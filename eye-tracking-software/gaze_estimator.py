"""Gaze estimation: feature extraction from MediaPipe landmarks + regression."""

import os
import numpy as np
import cv2
import mediapipe as mp
from sklearn.linear_model import Ridge
from sklearn.preprocessing import PolynomialFeatures
from sklearn.pipeline import Pipeline
from sklearn.model_selection import cross_val_score
from sklearn.gaussian_process import GaussianProcessRegressor
from sklearn.gaussian_process.kernels import RBF, WhiteKernel

# MediaPipe Face Mesh landmark indices
# Left eye corners
LEFT_EYE_INNER = 133
LEFT_EYE_OUTER = 33
LEFT_EYE_TOP = 159
LEFT_EYE_BOTTOM = 145

# Right eye corners
RIGHT_EYE_INNER = 362
RIGHT_EYE_OUTER = 263
RIGHT_EYE_TOP = 386
RIGHT_EYE_BOTTOM = 374

# Iris landmarks (MediaPipe iris refinement)
LEFT_IRIS = [468, 469, 470, 471, 472]   # centre, right, top, left, bottom
RIGHT_IRIS = [473, 474, 475, 476, 477]  # centre, right, top, left, bottom

# 3D model points for head pose estimation (generic face model)
MODEL_POINTS = np.array([
    (0.0, 0.0, 0.0),             # Nose tip (1)
    (0.0, -330.0, -65.0),        # Chin (152)
    (-225.0, 170.0, -135.0),     # Left eye left corner (33)
    (225.0, 170.0, -135.0),      # Right eye right corner (263)
    (-150.0, -150.0, -125.0),    # Left mouth corner (61)
    (150.0, -150.0, -125.0),     # Right mouth corner (291)
], dtype=np.float64)

# Corresponding MediaPipe landmark indices
POSE_LANDMARK_IDS = [1, 152, 33, 263, 61, 291]

# Path to face landmarker model (next to this script)
MODEL_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "face_landmarker.task")


class GazeEstimator:
    """Extracts eye/gaze features and runs gaze regression."""

    def __init__(self):
        BaseOptions = mp.tasks.BaseOptions
        FaceLandmarker = mp.tasks.vision.FaceLandmarker
        FaceLandmarkerOptions = mp.tasks.vision.FaceLandmarkerOptions
        RunningMode = mp.tasks.vision.RunningMode

        options = FaceLandmarkerOptions(
            base_options=BaseOptions(model_asset_path=MODEL_PATH),
            running_mode=RunningMode.VIDEO,
            num_faces=1,
            min_face_detection_confidence=0.5,
            min_tracking_confidence=0.5,
            output_face_blendshapes=False,
            output_facial_transformation_matrixes=False,
        )
        self.landmarker = FaceLandmarker.create_from_options(options)
        self._timestamp_ms = 0

        self.model_x = None
        self.model_y = None
        self._camera_matrix = None
        self._dist_coeffs = np.zeros((4, 1), dtype=np.float64)

    def _get_camera_matrix(self, frame_width, frame_height):
        """Build approximate camera intrinsic matrix."""
        if self._camera_matrix is None or self._camera_matrix[0, 2] != frame_width / 2:
            focal_length = frame_width
            center = (frame_width / 2, frame_height / 2)
            self._camera_matrix = np.array([
                [focal_length, 0, center[0]],
                [0, focal_length, center[1]],
                [0, 0, 1],
            ], dtype=np.float64)
        return self._camera_matrix

    def process_frame(self, frame):
        """Process a BGR frame and return (features, confidence, landmarks) or (None, 0, None).

        landmarks is the list of NormalizedLandmark for the first face, or None.
        """
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)

        self._timestamp_ms += 33  # ~30fps
        result = self.landmarker.detect_for_video(mp_image, self._timestamp_ms)

        if not result.face_landmarks:
            return None, 0.0, None

        face = result.face_landmarks[0]  # list of NormalizedLandmark
        h, w = frame.shape[:2]

        if len(face) < 478:
            # No iris landmarks available
            return None, 0.0, None

        # Extract iris centres
        left_iris_center = self._get_landmark_point(face, LEFT_IRIS[0], w, h)
        right_iris_center = self._get_landmark_point(face, RIGHT_IRIS[0], w, h)

        # Extract eye corners
        left_inner = self._get_landmark_point(face, LEFT_EYE_INNER, w, h)
        left_outer = self._get_landmark_point(face, LEFT_EYE_OUTER, w, h)
        left_top = self._get_landmark_point(face, LEFT_EYE_TOP, w, h)
        left_bottom = self._get_landmark_point(face, LEFT_EYE_BOTTOM, w, h)

        right_inner = self._get_landmark_point(face, RIGHT_EYE_INNER, w, h)
        right_outer = self._get_landmark_point(face, RIGHT_EYE_OUTER, w, h)
        right_top = self._get_landmark_point(face, RIGHT_EYE_TOP, w, h)
        right_bottom = self._get_landmark_point(face, RIGHT_EYE_BOTTOM, w, h)

        # Normalised iris position within eye bounding box
        left_iris_norm = self._normalise_iris(
            left_iris_center, left_outer, left_inner, left_top, left_bottom
        )
        right_iris_norm = self._normalise_iris(
            right_iris_center, right_inner, right_outer, right_top, right_bottom
        )

        # Head pose
        yaw, pitch = self._estimate_head_pose(face, w, h)

        features = np.array([
            left_iris_norm[0], left_iris_norm[1],
            right_iris_norm[0], right_iris_norm[1],
            yaw, pitch,
        ])

        # Confidence: based on head pose (penalise extreme angles)
        pose_penalty = max(0, 1.0 - (abs(yaw) + abs(pitch)) / 60.0)
        confidence = float(np.clip(0.9 * pose_penalty, 0, 1))

        return features, confidence, face

    def _get_landmark_point(self, face, idx, w, h):
        """Get 2D pixel coordinates for a landmark."""
        lm = face[idx]
        return np.array([lm.x * w, lm.y * h])

    def _normalise_iris(self, iris_center, eye_left, eye_right, eye_top, eye_bottom):
        """Normalise iris position within eye bounding box to [0,1]."""
        eye_width = np.linalg.norm(eye_right - eye_left)
        eye_height = np.linalg.norm(eye_bottom - eye_top)

        if eye_width < 1 or eye_height < 1:
            return np.array([0.5, 0.5])

        # Project iris onto eye axis
        eye_horizontal = eye_right - eye_left
        eye_vertical = eye_bottom - eye_top
        iris_relative = iris_center - eye_left

        norm_x = np.dot(iris_relative, eye_horizontal) / (eye_width ** 2)
        norm_y = np.dot(iris_relative, eye_vertical) / (eye_height ** 2)

        return np.array([np.clip(norm_x, 0, 1), np.clip(norm_y, 0, 1)])

    def _estimate_head_pose(self, face, w, h):
        """Estimate head yaw and pitch using solvePnP."""
        image_points = np.array([
            self._get_landmark_point(face, idx, w, h)
            for idx in POSE_LANDMARK_IDS
        ], dtype=np.float64)

        camera_matrix = self._get_camera_matrix(w, h)
        success, rotation_vec, _ = cv2.solvePnP(
            MODEL_POINTS, image_points, camera_matrix, self._dist_coeffs,
            flags=cv2.SOLVEPNP_ITERATIVE,
        )

        if not success:
            return 0.0, 0.0

        rmat, _ = cv2.Rodrigues(rotation_vec)
        # Decompose rotation matrix to Euler angles
        sy = np.sqrt(rmat[0, 0] ** 2 + rmat[1, 0] ** 2)
        pitch = np.degrees(np.arctan2(-rmat[2, 0], sy))
        yaw = np.degrees(np.arctan2(rmat[2, 1], rmat[2, 2]))

        return float(yaw), float(pitch)

    def train_model(self, features_list, screen_points):
        """Train gaze regression models.

        Args:
            features_list: array of shape (N, 6) - feature vectors
            screen_points: array of shape (N, 2) - screen (x, y) coordinates

        Returns:
            (mean_error_x, mean_error_y) from cross-validation
        """
        X = np.array(features_list)
        y_x = np.array([p[0] for p in screen_points])
        y_y = np.array([p[1] for p in screen_points])

        # Try Ridge with polynomial features
        ridge_pipe = Pipeline([
            ('poly', PolynomialFeatures(degree=2, include_bias=False)),
            ('ridge', Ridge(alpha=1.0)),
        ])

        # Cross-validate Ridge
        n_splits = min(5, len(X))
        if n_splits >= 2:
            ridge_scores_x = -cross_val_score(ridge_pipe, X, y_x, cv=n_splits, scoring='neg_mean_absolute_error')
            ridge_scores_y = -cross_val_score(ridge_pipe, X, y_y, cv=n_splits, scoring='neg_mean_absolute_error')
            ridge_error = (ridge_scores_x.mean() + ridge_scores_y.mean()) / 2
        else:
            ridge_error = float('inf')

        # Try Gaussian Process
        gp_error = float('inf')
        if len(X) <= 50:  # GP is slow with many points
            try:
                kernel = RBF(length_scale=1.0) + WhiteKernel(noise_level=1.0)
                gp = GaussianProcessRegressor(kernel=kernel, n_restarts_optimizer=2)
                if n_splits >= 2:
                    gp_scores_x = -cross_val_score(gp, X, y_x, cv=n_splits, scoring='neg_mean_absolute_error')
                    gp_scores_y = -cross_val_score(gp, X, y_y, cv=n_splits, scoring='neg_mean_absolute_error')
                    gp_error = (gp_scores_x.mean() + gp_scores_y.mean()) / 2
            except Exception:
                pass

        # Pick the better model
        if gp_error < ridge_error:
            kernel = RBF(length_scale=1.0) + WhiteKernel(noise_level=1.0)
            self.model_x = GaussianProcessRegressor(kernel=kernel, n_restarts_optimizer=2)
            self.model_y = GaussianProcessRegressor(kernel=kernel, n_restarts_optimizer=2)
        else:
            self.model_x = Pipeline([
                ('poly', PolynomialFeatures(degree=2, include_bias=False)),
                ('ridge', Ridge(alpha=1.0)),
            ])
            self.model_y = Pipeline([
                ('poly', PolynomialFeatures(degree=2, include_bias=False)),
                ('ridge', Ridge(alpha=1.0)),
            ])

        self.model_x.fit(X, y_x)
        self.model_y.fit(X, y_y)

        # Return training errors
        pred_x = self.model_x.predict(X)
        pred_y = self.model_y.predict(X)
        err_x = np.mean(np.abs(pred_x - y_x))
        err_y = np.mean(np.abs(pred_y - y_y))
        return err_x, err_y

    def predict(self, features):
        """Predict screen coordinates from feature vector."""
        if self.model_x is None or self.model_y is None:
            return None
        X = features.reshape(1, -1)
        sx = float(self.model_x.predict(X)[0])
        sy = float(self.model_y.predict(X)[0])
        return sx, sy

    def close(self):
        """Release resources."""
        self.landmarker.close()
