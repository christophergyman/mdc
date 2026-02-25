"""Transparent click-through crosshair overlay window."""

import time
import objc
import AppKit
import Quartz
from Foundation import NSObject, NSTimer, NSRunLoop, NSDefaultRunLoopMode
from AppKit import (
    NSWindow, NSScreen, NSView, NSColor, NSFont,
    NSWindowStyleMaskBorderless, NSBackingStoreBuffered,
)


class CrosshairView(NSView):
    """Draws the crosshair at the current gaze position."""

    def initWithFrame_(self, frame):
        self = objc.super(CrosshairView, self).initWithFrame_(frame)
        if self is None:
            return None
        self._gaze_x = 0
        self._gaze_y = 0
        self._opacity = 1.0
        self._color_r = 1.0
        self._color_g = 1.0
        self._color_b = 1.0
        self._arm_length = 40
        self._line_width = 1.5
        self._gap = 6
        return self

    def drawRect_(self, rect):
        if self._opacity <= 0.01:
            return

        bounds = self.bounds()
        sh = bounds.size.height

        # Gaze position in AppKit coords (flip Y)
        x = self._gaze_x
        y = sh - self._gaze_y

        arm = self._arm_length
        gap = self._gap
        lw = self._line_width

        # Drop shadow (thin black outline)
        shadow_color = NSColor.colorWithCalibratedRed_green_blue_alpha_(0.0, 0.0, 0.0, 0.5 * self._opacity)
        shadow_color.setStroke()
        self._draw_crosshair(x, y, arm, gap, lw + 1.5)

        # Main crosshair
        main_color = NSColor.colorWithCalibratedRed_green_blue_alpha_(
            self._color_r, self._color_g, self._color_b, self._opacity
        )
        main_color.setStroke()
        self._draw_crosshair(x, y, arm, gap, lw)

    def _draw_crosshair(self, x, y, arm, gap, line_width):
        """Draw a crosshair (+) shape with centre gap."""
        path = AppKit.NSBezierPath.bezierPath()
        path.setLineWidth_(line_width)
        path.setLineCapStyle_(AppKit.NSLineCapStyleRound)

        # Top arm
        path.moveToPoint_((x, y + gap))
        path.lineToPoint_((x, y + arm))

        # Bottom arm
        path.moveToPoint_((x, y - gap))
        path.lineToPoint_((x, y - arm))

        # Right arm
        path.moveToPoint_((x + gap, y))
        path.lineToPoint_((x + arm, y))

        # Left arm
        path.moveToPoint_((x - gap, y))
        path.lineToPoint_((x - arm, y))

        path.stroke()

    def isOpaque(self):
        return False


class OverlayController:
    """Manages the transparent crosshair overlay window."""

    def __init__(self, settings):
        self.settings = settings
        self.visible = True

        # Smoothing state
        self._smoothed_x = 0.0
        self._smoothed_y = 0.0
        self._first_update = True

        # Face loss fade
        self._face_detected = True
        self._face_lost_time = 0.0
        self._target_opacity = 1.0
        self._current_opacity = 1.0

        screen = NSScreen.mainScreen()
        self.screen_frame = screen.frame()
        self.screen_width = self.screen_frame.size.width
        self.screen_height = self.screen_frame.size.height

        self._setup_window()

    def _setup_window(self):
        """Create the transparent overlay window."""
        self.window = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            self.screen_frame,
            NSWindowStyleMaskBorderless,
            NSBackingStoreBuffered,
            False,
        )
        self.window.setLevel_(AppKit.NSStatusWindowLevel)
        self.window.setBackgroundColor_(NSColor.clearColor())
        self.window.setOpaque_(False)
        self.window.setHasShadow_(False)
        self.window.setIgnoresMouseEvents_(True)
        self.window.setCollectionBehavior_(
            AppKit.NSWindowCollectionBehaviorCanJoinAllSpaces |
            AppKit.NSWindowCollectionBehaviorStationary
        )
        self.window.setAlphaValue_(1.0)

        self.view = CrosshairView.alloc().initWithFrame_(self.screen_frame)
        self.window.setContentView_(self.view)
        self._apply_settings()

    def _apply_settings(self):
        """Apply current settings to the crosshair view."""
        self.view._color_r = self.settings.crosshair_color_r
        self.view._color_g = self.settings.crosshair_color_g
        self.view._color_b = self.settings.crosshair_color_b
        self.view._arm_length = self.settings.crosshair_size
        self.view._line_width = self.settings.crosshair_line_width
        self.view._gap = self.settings.crosshair_gap

    def show(self):
        """Show the overlay window."""
        self.window.makeKeyAndOrderFront_(None)
        self.window.setIgnoresMouseEvents_(True)
        self.visible = True

    def hide(self):
        """Hide the overlay window."""
        self.window.orderOut_(None)
        self.visible = False

    def toggle(self):
        """Toggle overlay visibility."""
        if self.visible:
            self.hide()
        else:
            self.show()

    def update_gaze(self, raw_x, raw_y, face_detected, confidence):
        """Update the crosshair position with smoothing and face-loss handling."""
        now = time.time()
        alpha = self.settings.smoothing_alpha

        if face_detected:
            # Clamp to screen bounds
            raw_x = max(0, min(raw_x, self.screen_width))
            raw_y = max(0, min(raw_y, self.screen_height))

            if self._first_update:
                self._smoothed_x = raw_x
                self._smoothed_y = raw_y
                self._first_update = False
            else:
                self._smoothed_x = alpha * raw_x + (1 - alpha) * self._smoothed_x
                self._smoothed_y = alpha * raw_y + (1 - alpha) * self._smoothed_y

            self.view._gaze_x = self._smoothed_x
            self.view._gaze_y = self._smoothed_y

            if not self._face_detected:
                # Face re-detected - fade in over 0.3s
                self._face_detected = True
            self._target_opacity = 1.0
        else:
            if self._face_detected:
                # Face just lost
                self._face_lost_time = now
                self._face_detected = False

            # Fade out over 0.8s after face loss
            time_since_loss = now - self._face_lost_time
            if time_since_loss < 0.8:
                self._target_opacity = 1.0 - (time_since_loss / 0.8)
            else:
                self._target_opacity = 0.0

        # Smooth opacity changes
        opacity_speed = 0.15  # lerp speed
        self._current_opacity += (self._target_opacity - self._current_opacity) * opacity_speed
        self.view._opacity = max(0, min(1, self._current_opacity))

        if self.visible:
            self.view.setNeedsDisplay_(True)

    def update_settings(self, settings):
        """Update appearance from settings."""
        self.settings = settings
        self._apply_settings()
        self.view.setNeedsDisplay_(True)
