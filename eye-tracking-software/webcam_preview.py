"""Webcam preview window with MediaPipe landmark overlays."""

import cv2
import numpy as np
import objc
import AppKit
from Foundation import NSObject, NSMakeRect
from AppKit import (
    NSWindow, NSView, NSColor, NSFont, NSImage, NSScreen,
    NSWindowStyleMaskTitled, NSWindowStyleMaskClosable, NSWindowStyleMaskMiniaturizable,
    NSBackingStoreBuffered, NSImageView, NSBitmapImageRep,
    NSCompositingOperationSourceOver, NSScaleProportionally,
    NSImageScaleProportionallyUpOrDown,
)
import mediapipe as mp

# Key landmark indices for visualization
LEFT_EYE_CONTOUR = [33, 7, 163, 144, 145, 153, 154, 155, 133, 173, 157, 158, 159, 160, 161, 246]
RIGHT_EYE_CONTOUR = [362, 382, 381, 380, 374, 373, 390, 249, 263, 466, 388, 387, 386, 385, 384, 398]
LEFT_IRIS = [468, 469, 470, 471, 472]
RIGHT_IRIS = [473, 474, 475, 476, 477]
FACE_OUTLINE = [10, 338, 297, 332, 284, 251, 389, 356, 454, 323, 361, 288, 397, 365, 379, 378,
                400, 377, 152, 148, 176, 149, 150, 136, 172, 58, 132, 93, 234, 127, 162, 21,
                54, 103, 67, 109]

PREVIEW_WIDTH = 320
PREVIEW_HEIGHT = 240


class WebcamPreviewController:
    """Manages the webcam preview window."""

    def __init__(self, settings, on_position_changed=None):
        self.settings = settings
        self.on_position_changed = on_position_changed
        self._setup_window()

    def _setup_window(self):
        x = self.settings.webcam_preview_x
        y = self.settings.webcam_preview_y
        frame = NSMakeRect(x, y, PREVIEW_WIDTH, PREVIEW_HEIGHT)

        self.window = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            frame,
            NSWindowStyleMaskTitled | NSWindowStyleMaskClosable | NSWindowStyleMaskMiniaturizable,
            NSBackingStoreBuffered,
            False,
        )
        self.window.setTitle_("Webcam Preview")
        self.window.setReleasedWhenClosed_(False)

        self._image_view = NSImageView.alloc().initWithFrame_(
            NSMakeRect(0, 0, PREVIEW_WIDTH, PREVIEW_HEIGHT)
        )
        self._image_view.setImageScaling_(NSImageScaleProportionallyUpOrDown)
        self.window.setContentView_(self._image_view)

    def show(self):
        self.window.makeKeyAndOrderFront_(None)

    def hide(self):
        self.window.orderOut_(None)

    def is_visible(self):
        return self.window.isVisible()

    def update_frame(self, frame, face_landmarks=None):
        """Update the preview with a new frame and optional landmark overlay.

        Args:
            frame: BGR numpy array from webcam
            face_landmarks: MediaPipe face landmarks (or None)
        """
        display = frame.copy()
        h, w = display.shape[:2]

        if face_landmarks is not None:
            self._draw_landmarks(display, face_landmarks, w, h)

        # Resize
        display = cv2.resize(display, (PREVIEW_WIDTH, PREVIEW_HEIGHT))

        # Convert BGR to RGB
        rgb = cv2.cvtColor(display, cv2.COLOR_BGR2RGB)
        rh, rw, rc = rgb.shape
        bytes_per_row = rc * rw

        bitmap = NSBitmapImageRep.alloc().initWithBitmapDataPlanes_pixelsWide_pixelsHigh_bitsPerSample_samplesPerPixel_hasAlpha_isPlanar_colorSpaceName_bytesPerRow_bitsPerPixel_(
            (rgb.tobytes(), None, None, None, None),
            rw, rh, 8, 3, False, False, AppKit.NSCalibratedRGBColorSpace, bytes_per_row, 24
        )
        if bitmap:
            image = NSImage.alloc().initWithSize_((rw, rh))
            image.addRepresentation_(bitmap)
            self._image_view.setImage_(image)

    def _draw_landmarks(self, frame, face, w, h):
        """Draw eye contours, iris, and face outline on frame."""
        def get_pt(idx):
            lm = face[idx]
            return (int(lm.x * w), int(lm.y * h))

        # Face outline
        pts = [get_pt(i) for i in FACE_OUTLINE]
        for i in range(len(pts) - 1):
            cv2.line(frame, pts[i], pts[i + 1], (100, 100, 100), 1)
        cv2.line(frame, pts[-1], pts[0], (100, 100, 100), 1)

        # Left eye contour
        pts = [get_pt(i) for i in LEFT_EYE_CONTOUR]
        for i in range(len(pts) - 1):
            cv2.line(frame, pts[i], pts[i + 1], (0, 255, 0), 1)
        cv2.line(frame, pts[-1], pts[0], (0, 255, 0), 1)

        # Right eye contour
        pts = [get_pt(i) for i in RIGHT_EYE_CONTOUR]
        for i in range(len(pts) - 1):
            cv2.line(frame, pts[i], pts[i + 1], (0, 255, 0), 1)
        cv2.line(frame, pts[-1], pts[0], (0, 255, 0), 1)

        # Left iris
        center = get_pt(LEFT_IRIS[0])
        for idx in LEFT_IRIS[1:]:
            pt = get_pt(idx)
            cv2.line(frame, center, pt, (0, 200, 255), 1)
        cv2.circle(frame, center, 3, (0, 200, 255), -1)

        # Right iris
        center = get_pt(RIGHT_IRIS[0])
        for idx in RIGHT_IRIS[1:]:
            pt = get_pt(idx)
            cv2.line(frame, center, pt, (0, 200, 255), 1)
        cv2.circle(frame, center, 3, (0, 200, 255), -1)

    def save_position(self):
        """Save current window position to settings."""
        if self.on_position_changed:
            frame = self.window.frame()
            self.on_position_changed(frame.origin.x, frame.origin.y)
