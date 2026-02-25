"""Calibration routine: fullscreen target display, data collection, model training."""

import time
import numpy as np
import cv2
import objc
import AppKit
import Quartz
from Foundation import NSObject, NSTimer, NSRunLoop, NSDefaultRunLoopMode
from AppKit import (
    NSWindow, NSScreen, NSView, NSColor, NSFont,
    NSWindowStyleMaskBorderless, NSBackingStoreBuffered,
    NSApplication, NSButton,
    NSBezelStyleRounded, NSTextField, NSImageView, NSImage,
    NSBitmapImageRep, NSCompositingOperationSourceOver,
)


def generate_calibration_points(screen_width, screen_height, cols=5, rows=4):
    """Generate calibration points in a grid covering the screen with margins."""
    margin_x = screen_width * 0.05
    margin_y = screen_height * 0.05
    points = []
    for row in range(rows):
        for col in range(cols):
            x = margin_x + col * (screen_width - 2 * margin_x) / (cols - 1)
            y = margin_y + row * (screen_height - 2 * margin_y) / (rows - 1)
            points.append((x, y))
    return points


class CalibrationView(NSView):
    """Custom view for drawing calibration targets and results."""

    def initWithFrame_(self, frame):
        self = objc.super(CalibrationView, self).initWithFrame_(frame)
        if self is None:
            return None
        self._target_x = 0
        self._target_y = 0
        self._target_scale = 0.0
        self._target_visible = False
        self._progress_text = ""
        self._instruction_text = ""
        self._phase = "calibrating"  # calibrating, results, instructions
        self._result_points = []     # list of (target_x, target_y, pred_x, pred_y, error_px)
        self._mean_error = 0.0
        self._mean_error_pct = 0.0
        self._show_warning = False
        self._webcam_image = None
        self._show_accept_redo = False
        return self

    def drawRect_(self, rect):
        NSColor.blackColor().setFill()
        AppKit.NSRectFill(rect)

        bounds = self.bounds()
        sw = bounds.size.width
        sh = bounds.size.height

        if self._phase == "instructions":
            self._draw_instructions(sw, sh)
        elif self._phase == "calibrating":
            self._draw_calibration_target(sw, sh)
        elif self._phase == "results":
            self._draw_results(sw, sh)

    def _draw_instructions(self, sw, sh):
        """Draw pre-calibration instruction screen."""
        attrs = {
            AppKit.NSFontAttributeName: NSFont.systemFontOfSize_(24),
            AppKit.NSForegroundColorAttributeName: NSColor.whiteColor(),
        }
        lines = [
            "Calibration",
            "",
            "Keep your head still throughout calibration",
            "Look at each dot as it appears",
            "Try to keep your face centred in the camera",
            "",
            "Press any key or click to begin...    (Esc to cancel)",
        ]
        title_attrs = {
            AppKit.NSFontAttributeName: NSFont.boldSystemFontOfSize_(36),
            AppKit.NSForegroundColorAttributeName: NSColor.whiteColor(),
        }
        y = sh * 0.65
        for i, line in enumerate(lines):
            a = title_attrs if i == 0 else attrs
            s = AppKit.NSAttributedString.alloc().initWithString_attributes_(line, a)
            size = s.size()
            s.drawAtPoint_((sw / 2 - size.width / 2, y))
            y -= size.height + 8

        # Draw webcam preview if available
        if self._webcam_image is not None:
            self._webcam_image.drawInRect_fromRect_operation_fraction_(
                ((sw - 180, 10), (160, 120)),
                ((0, 0), (self._webcam_image.size().width, self._webcam_image.size().height)),
                NSCompositingOperationSourceOver,
                0.8,
            )

    def _draw_calibration_target(self, sw, sh):
        """Draw the animated target dot and progress text."""
        if self._target_visible and self._target_scale > 0:
            radius = 12 * self._target_scale
            x = self._target_x - radius
            # Flip Y for AppKit coordinate system (origin bottom-left)
            y = (sh - self._target_y) - radius
            oval_rect = ((x, y), (radius * 2, radius * 2))

            # Outer glow
            glow_color = NSColor.colorWithCalibratedRed_green_blue_alpha_(0.3, 0.6, 1.0, 0.3 * self._target_scale)
            glow_color.setFill()
            glow_radius = radius * 2
            glow_rect = ((self._target_x - glow_radius, (sh - self._target_y) - glow_radius),
                         (glow_radius * 2, glow_radius * 2))
            path = AppKit.NSBezierPath.bezierPathWithOvalInRect_(glow_rect)
            path.fill()

            # Main dot
            dot_color = NSColor.colorWithCalibratedRed_green_blue_alpha_(0.4, 0.7, 1.0, self._target_scale)
            dot_color.setFill()
            path = AppKit.NSBezierPath.bezierPathWithOvalInRect_(oval_rect)
            path.fill()

            # Centre bright spot
            center_radius = radius * 0.4
            center_rect = ((self._target_x - center_radius, (sh - self._target_y) - center_radius),
                           (center_radius * 2, center_radius * 2))
            NSColor.whiteColor().setFill()
            path = AppKit.NSBezierPath.bezierPathWithOvalInRect_(center_rect)
            path.fill()

        # Progress text
        if self._progress_text:
            attrs = {
                AppKit.NSFontAttributeName: NSFont.systemFontOfSize_(18),
                AppKit.NSForegroundColorAttributeName: NSColor.colorWithCalibratedWhite_alpha_(0.7, 1.0),
            }
            s = AppKit.NSAttributedString.alloc().initWithString_attributes_(self._progress_text, attrs)
            size = s.size()
            s.drawAtPoint_((sw / 2 - size.width / 2, 30))

        # Instruction text
        if self._instruction_text:
            attrs = {
                AppKit.NSFontAttributeName: NSFont.systemFontOfSize_(14),
                AppKit.NSForegroundColorAttributeName: NSColor.colorWithCalibratedWhite_alpha_(0.5, 1.0),
            }
            s = AppKit.NSAttributedString.alloc().initWithString_attributes_(self._instruction_text, attrs)
            size = s.size()
            s.drawAtPoint_((sw / 2 - size.width / 2, 60))

        # Webcam preview
        if self._webcam_image is not None:
            self._webcam_image.drawInRect_fromRect_operation_fraction_(
                ((sw - 180, 10), (160, 120)),
                ((0, 0), (self._webcam_image.size().width, self._webcam_image.size().height)),
                NSCompositingOperationSourceOver,
                0.7,
            )

    def _draw_results(self, sw, sh):
        """Draw calibration accuracy results."""
        # Title
        title_attrs = {
            AppKit.NSFontAttributeName: NSFont.boldSystemFontOfSize_(28),
            AppKit.NSForegroundColorAttributeName: NSColor.whiteColor(),
        }
        title = AppKit.NSAttributedString.alloc().initWithString_attributes_("Calibration Results", title_attrs)
        ts = title.size()
        title.drawAtPoint_((sw / 2 - ts.width / 2, sh - 60))

        # Draw target/prediction pairs
        for (tx, ty, px, py, err) in self._result_points:
            # Flip Y
            ty_f = sh - ty
            py_f = sh - py

            # Target point (green circle)
            r = 6
            NSColor.greenColor().setFill()
            path = AppKit.NSBezierPath.bezierPathWithOvalInRect_(((tx - r, ty_f - r), (r * 2, r * 2)))
            path.fill()

            # Predicted point (red circle)
            NSColor.redColor().setFill()
            path = AppKit.NSBezierPath.bezierPathWithOvalInRect_(((px - r, py_f - r), (r * 2, r * 2)))
            path.fill()

            # Line between them
            NSColor.colorWithCalibratedWhite_alpha_(0.4, 1.0).setStroke()
            line = AppKit.NSBezierPath.bezierPath()
            line.moveToPoint_((tx, ty_f))
            line.lineToPoint_((px, py_f))
            line.setLineWidth_(1.0)
            line.stroke()

        # Stats text
        stats_attrs = {
            AppKit.NSFontAttributeName: NSFont.systemFontOfSize_(18),
            AppKit.NSForegroundColorAttributeName: NSColor.whiteColor(),
        }
        stats_text = f"Mean error: {self._mean_error:.0f}px ({self._mean_error_pct:.1f}% of screen)"
        s = AppKit.NSAttributedString.alloc().initWithString_attributes_(stats_text, stats_attrs)
        ss = s.size()
        s.drawAtPoint_((sw / 2 - ss.width / 2, sh - 100))

        if self._show_warning:
            warn_attrs = {
                AppKit.NSFontAttributeName: NSFont.boldSystemFontOfSize_(16),
                AppKit.NSForegroundColorAttributeName: NSColor.yellowColor(),
            }
            warn = AppKit.NSAttributedString.alloc().initWithString_attributes_(
                "Warning: High calibration error. Consider recalibrating.", warn_attrs
            )
            ws = warn.size()
            warn.drawAtPoint_((sw / 2 - ws.width / 2, sh - 130))

        # Legend
        legend_attrs = {
            AppKit.NSFontAttributeName: NSFont.systemFontOfSize_(14),
            AppKit.NSForegroundColorAttributeName: NSColor.colorWithCalibratedWhite_alpha_(0.6, 1.0),
        }
        legend = AppKit.NSAttributedString.alloc().initWithString_attributes_(
            "Green = target    Red = predicted gaze    Click 'Accept' or 'Redo'", legend_attrs
        )
        ls = legend.size()
        legend.drawAtPoint_((sw / 2 - ls.width / 2, 80))

    def isFlipped(self):
        return False


class CalibrationController:
    """Manages the calibration window and data collection process."""

    def __init__(self, gaze_estimator, webcam_capture, on_complete, on_cancel=None):
        """
        Args:
            gaze_estimator: GazeEstimator instance
            webcam_capture: cv2.VideoCapture instance
            on_complete: callback(success: bool) called when calibration finishes
            on_cancel: optional callback() if user cancels
        """
        self.estimator = gaze_estimator
        self.capture = webcam_capture
        self.on_complete = on_complete
        self.on_cancel = on_cancel

        screen = NSScreen.mainScreen()
        self.screen_frame = screen.frame()
        self.screen_width = self.screen_frame.size.width
        self.screen_height = self.screen_frame.size.height

        self.points = generate_calibration_points(self.screen_width, self.screen_height)
        self.collected_features = []
        self.collected_screen_pts = []

        self.current_point_idx = 0
        self.state = "instructions"  # instructions, animating, settling, collecting, results
        self.state_start_time = 0
        self.frame_features_buffer = []
        self._last_frame = None

        self._setup_window()
        self._timer = None
        self._accept_button = None
        self._redo_button = None

    def _setup_window(self):
        """Create the fullscreen calibration window."""
        self.window = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            self.screen_frame,
            NSWindowStyleMaskBorderless,
            NSBackingStoreBuffered,
            False,
        )
        self.window.setLevel_(AppKit.NSStatusWindowLevel)
        self.window.setBackgroundColor_(NSColor.blackColor())
        self.window.setOpaque_(True)
        self.window.setHasShadow_(False)
        self.window.setCollectionBehavior_(AppKit.NSWindowCollectionBehaviorCanJoinAllSpaces)

        self.view = CalibrationView.alloc().initWithFrame_(self.screen_frame)
        self.view._phase = "instructions"
        self.window.setContentView_(self.view)

    def start(self):
        """Begin the calibration sequence."""
        self.window.makeKeyAndOrderFront_(None)
        self.window.makeFirstResponder_(self.view)
        self.state = "instructions"
        self.view._phase = "instructions"
        self.view.setNeedsDisplay_(True)

        # Start the update timer (60fps for smooth animation)
        self._timer = NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
            1.0 / 60.0, self, "tick:", None, True
        )
        NSRunLoop.currentRunLoop().addTimer_forMode_(self._timer, NSDefaultRunLoopMode)

        # Listen for key/click to start
        self._event_monitor = AppKit.NSEvent.addLocalMonitorForEventsMatchingMask_handler_(
            AppKit.NSEventMaskKeyDown | AppKit.NSEventMaskLeftMouseDown,
            self._handle_start_event,
        )

        # Listen for Escape to cancel at any time
        self._escape_monitor = AppKit.NSEvent.addLocalMonitorForEventsMatchingMask_handler_(
            AppKit.NSEventMaskKeyDown,
            self._handle_escape_event,
        )

    def _handle_start_event(self, event):
        if self.state == "instructions":
            # Don't start calibration on Escape — that's handled by _handle_escape_event
            if hasattr(event, 'keyCode') and event.keyCode() == 53:
                return event
            self.state = "animating"
            self.state_start_time = time.time()
            self.current_point_idx = 0
            self.view._phase = "calibrating"
            self.view._instruction_text = "Keep your head still and look at each dot"
            self._update_target_position()
            AppKit.NSEvent.removeMonitor_(self._event_monitor)
            self._event_monitor = None
        return event

    def _handle_escape_event(self, event):
        """Cancel calibration when Escape is pressed."""
        if event.keyCode() == 53:  # Escape
            self.cancel()
            return None  # Consume the event
        return event

    def tick_(self, timer):
        """Called every frame to update calibration state."""
        now = time.time()
        elapsed = now - self.state_start_time

        if self.state == "animating":
            # Scale-in animation over 0.3s
            progress = min(elapsed / 0.3, 1.0)
            # Ease-out
            self.view._target_scale = 1.0 - (1.0 - progress) ** 3
            self.view._target_visible = True
            if progress >= 1.0:
                self.state = "settling"
                self.state_start_time = now

        elif self.state == "settling":
            self.view._target_scale = 1.0
            # Wait 0.5s for user's eyes to settle
            if elapsed >= 0.5:
                self.state = "collecting"
                self.state_start_time = now
                self.frame_features_buffer = []

        elif self.state == "collecting":
            # Collect frames for 1.5s
            self._collect_frame()
            self.view._target_scale = 1.0
            if elapsed >= 1.5:
                self._finish_point_collection()

        elif self.state == "transitioning":
            # Brief pause between points
            self.view._target_visible = False
            if elapsed >= 0.15:
                if self.current_point_idx < len(self.points):
                    self.state = "animating"
                    self.state_start_time = now
                    self._update_target_position()
                else:
                    self._finish_calibration()

        # Update webcam preview
        self._update_webcam_preview()
        self.view.setNeedsDisplay_(True)

    def _update_target_position(self):
        """Set the target position for the current calibration point."""
        if self.current_point_idx < len(self.points):
            x, y = self.points[self.current_point_idx]
            self.view._target_x = x
            self.view._target_y = y
            self.view._progress_text = f"Point {self.current_point_idx + 1} of {len(self.points)}"

    def _collect_frame(self):
        """Capture a frame and extract features."""
        ret, frame = self.capture.read()
        if not ret:
            return
        self._last_frame = frame
        features, confidence, _ = self.estimator.process_frame(frame)
        if features is not None and confidence > 0.3:
            self.frame_features_buffer.append(features)

    def _update_webcam_preview(self):
        """Update the small webcam preview in calibration view."""
        if self._last_frame is None:
            ret, frame = self.capture.read()
            if not ret:
                return
            self._last_frame = frame
        frame = self._last_frame
        # Resize for thumbnail
        small = cv2.resize(frame, (160, 120))
        small_rgb = cv2.cvtColor(small, cv2.COLOR_BGR2RGB)
        h, w, c = small_rgb.shape
        bytes_per_row = c * w
        bitmap = NSBitmapImageRep.alloc().initWithBitmapDataPlanes_pixelsWide_pixelsHigh_bitsPerSample_samplesPerPixel_hasAlpha_isPlanar_colorSpaceName_bytesPerRow_bitsPerPixel_(
            (small_rgb.tobytes(), None, None, None, None),
            w, h, 8, 3, False, False, AppKit.NSCalibratedRGBColorSpace, bytes_per_row, 24
        )
        if bitmap:
            image = NSImage.alloc().initWithSize_((w, h))
            image.addRepresentation_(bitmap)
            self.view._webcam_image = image

    def _finish_point_collection(self):
        """Process collected frames for current calibration point."""
        if len(self.frame_features_buffer) >= 5:
            features_array = np.array(self.frame_features_buffer)

            # Remove outliers: discard features > 2 std from mean
            mean = np.mean(features_array, axis=0)
            std = np.std(features_array, axis=0) + 1e-8
            distances = np.max(np.abs(features_array - mean) / std, axis=1)
            mask = distances < 2.0
            filtered = features_array[mask]

            if len(filtered) >= 3:
                avg_features = np.mean(filtered, axis=0)
                self.collected_features.append(avg_features)
                self.collected_screen_pts.append(self.points[self.current_point_idx])

        self.current_point_idx += 1
        self.state = "transitioning"
        self.state_start_time = time.time()

    def _finish_calibration(self):
        """Train the model and show results."""
        if self._timer:
            self._timer.invalidate()
            self._timer = None

        if len(self.collected_features) < 10:
            self._show_failure("Not enough valid calibration points collected. "
                             f"Got {len(self.collected_features)}, need at least 10.")
            return

        # Train the model
        err_x, err_y = self.estimator.train_model(
            self.collected_features, self.collected_screen_pts
        )

        # Compute per-point errors
        result_points = []
        total_error = 0
        for feat, (tx, ty) in zip(self.collected_features, self.collected_screen_pts):
            pred = self.estimator.predict(feat)
            if pred:
                px, py = pred
                err = np.sqrt((px - tx) ** 2 + (py - ty) ** 2)
                result_points.append((tx, ty, px, py, err))
                total_error += err

        mean_error = total_error / len(result_points) if result_points else 999
        mean_error_pct = (mean_error / self.screen_width) * 100

        # Show results
        self.view._phase = "results"
        self.view._result_points = result_points
        self.view._mean_error = mean_error
        self.view._mean_error_pct = mean_error_pct
        self.view._show_warning = mean_error_pct > 5.0

        # Add Accept/Redo buttons
        self._add_result_buttons()
        self.view.setNeedsDisplay_(True)

    def _add_result_buttons(self):
        """Add Accept and Redo buttons to the results screen."""
        mid_x = self.screen_width / 2
        btn_y = 20

        self._accept_button = NSButton.alloc().initWithFrame_(((mid_x - 130, btn_y), (120, 40)))
        self._accept_button.setTitle_("Accept")
        self._accept_button.setBezelStyle_(NSBezelStyleRounded)
        self._accept_button.setTarget_(self)
        self._accept_button.setAction_(objc.selector(self._on_accept, signature=b"v@:@"))
        self.view.addSubview_(self._accept_button)

        self._redo_button = NSButton.alloc().initWithFrame_(((mid_x + 10, btn_y), (120, 40)))
        self._redo_button.setTitle_("Redo")
        self._redo_button.setBezelStyle_(NSBezelStyleRounded)
        self._redo_button.setTarget_(self)
        self._redo_button.setAction_(objc.selector(self._on_redo, signature=b"v@:@"))
        self.view.addSubview_(self._redo_button)

    def _on_accept(self, sender):
        """User accepted calibration results."""
        self._cleanup()
        self.on_complete(True)

    def _on_redo(self, sender):
        """User wants to redo calibration."""
        self._cleanup()
        # Reset state
        self.collected_features = []
        self.collected_screen_pts = []
        self.current_point_idx = 0
        self._setup_window()
        self.start()

    def _show_failure(self, message):
        """Show calibration failure with retry option."""
        self.view._phase = "results"
        self.view._result_points = []
        self.view._mean_error = 999
        self.view._mean_error_pct = 100
        self.view._show_warning = True
        self._add_result_buttons()
        self._accept_button.setEnabled_(False)
        self.view.setNeedsDisplay_(True)

    def _cleanup(self):
        """Remove the calibration window."""
        if self._timer:
            self._timer.invalidate()
            self._timer = None
        if self._event_monitor:
            AppKit.NSEvent.removeMonitor_(self._event_monitor)
            self._event_monitor = None
        if hasattr(self, '_escape_monitor') and self._escape_monitor:
            AppKit.NSEvent.removeMonitor_(self._escape_monitor)
            self._escape_monitor = None
        self.window.orderOut_(None)

    def cancel(self):
        """Cancel calibration."""
        self._cleanup()
        if self.on_cancel:
            self.on_cancel()
        else:
            self.on_complete(False)
