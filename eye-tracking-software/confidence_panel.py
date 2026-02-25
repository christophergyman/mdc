"""Draggable floating confidence/quality HUD panel."""

import objc
import AppKit
from Foundation import NSObject, NSPoint, NSRect, NSSize, NSMakeRect
from AppKit import (
    NSWindow, NSView, NSColor, NSFont, NSScreen,
    NSWindowStyleMaskBorderless, NSBackingStoreBuffered,
    NSFloatingWindowLevel, NSVisualEffectView,
    NSVisualEffectBlendingModeBehindWindow,
    NSVisualEffectMaterialDark,
    NSTrackingArea, NSTrackingActiveAlways, NSTrackingMouseEnteredAndExited,
    NSTrackingMouseMoved, NSTrackingInVisibleRect,
)


PANEL_WIDTH = 200
PANEL_HEIGHT = 80


class ConfidencePanelView(NSView):
    """Custom view for the confidence panel content."""

    def initWithFrame_(self, frame):
        self = objc.super(ConfidencePanelView, self).initWithFrame_(frame)
        if self is None:
            return None
        self._status = "Initializing"
        self._status_color = NSColor.grayColor()
        self._confidence = 0.0
        self._fps = 0.0
        self._show_fps = True
        self._dragging = False
        self._drag_offset = (0, 0)
        return self

    def drawRect_(self, rect):
        bounds = self.bounds()
        w = bounds.size.width
        h = bounds.size.height

        # Background is handled by the visual effect view parent
        # Draw content
        y_offset = h - 18

        # Status text
        status_attrs = {
            AppKit.NSFontAttributeName: NSFont.boldSystemFontOfSize_(13),
            AppKit.NSForegroundColorAttributeName: self._status_color,
        }
        status_str = AppKit.NSAttributedString.alloc().initWithString_attributes_(
            self._status, status_attrs
        )
        status_str.drawAtPoint_((10, y_offset))
        y_offset -= 22

        # Confidence bar
        bar_x = 10
        bar_y = y_offset
        bar_w = w - 20
        bar_h = 10

        # Background
        NSColor.colorWithCalibratedWhite_alpha_(0.2, 1.0).setFill()
        bar_bg = AppKit.NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(
            ((bar_x, bar_y), (bar_w, bar_h)), 4, 4
        )
        bar_bg.fill()

        # Fill
        fill_w = max(0, min(bar_w * self._confidence, bar_w))
        if self._confidence > 0.7:
            fill_color = NSColor.colorWithCalibratedRed_green_blue_alpha_(0.2, 0.8, 0.3, 1.0)
        elif self._confidence > 0.4:
            fill_color = NSColor.colorWithCalibratedRed_green_blue_alpha_(0.9, 0.7, 0.1, 1.0)
        else:
            fill_color = NSColor.colorWithCalibratedRed_green_blue_alpha_(0.9, 0.2, 0.2, 1.0)
        fill_color.setFill()
        bar_fill = AppKit.NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(
            ((bar_x, bar_y), (fill_w, bar_h)), 4, 4
        )
        bar_fill.fill()

        y_offset -= 20

        # FPS text
        if self._show_fps:
            fps_attrs = {
                AppKit.NSFontAttributeName: NSFont.systemFontOfSize_(11),
                AppKit.NSForegroundColorAttributeName: NSColor.colorWithCalibratedWhite_alpha_(0.6, 1.0),
            }
            fps_str = AppKit.NSAttributedString.alloc().initWithString_attributes_(
                f"{self._fps:.0f} fps", fps_attrs
            )
            fps_str.drawAtPoint_((10, y_offset))

        # Confidence percentage on right
        pct_attrs = {
            AppKit.NSFontAttributeName: NSFont.systemFontOfSize_(11),
            AppKit.NSForegroundColorAttributeName: NSColor.colorWithCalibratedWhite_alpha_(0.5, 1.0),
        }
        pct_str = AppKit.NSAttributedString.alloc().initWithString_attributes_(
            f"{self._confidence * 100:.0f}%", pct_attrs
        )
        pct_size = pct_str.size()
        pct_str.drawAtPoint_((w - pct_size.width - 10, y_offset))

    def isOpaque(self):
        return False

    def acceptsFirstMouse_(self, event):
        return True

    def mouseDown_(self, event):
        self._dragging = True
        window_frame = self.window().frame()
        mouse_loc = AppKit.NSEvent.mouseLocation()
        self._drag_offset = (
            mouse_loc.x - window_frame.origin.x,
            mouse_loc.y - window_frame.origin.y,
        )

    def mouseDragged_(self, event):
        if self._dragging:
            mouse_loc = AppKit.NSEvent.mouseLocation()
            new_x = mouse_loc.x - self._drag_offset[0]
            new_y = mouse_loc.y - self._drag_offset[1]
            self.window().setFrameOrigin_((new_x, new_y))

    def mouseUp_(self, event):
        self._dragging = False
        # Save position
        if hasattr(self, '_on_position_changed') and self._on_position_changed:
            frame = self.window().frame()
            self._on_position_changed(frame.origin.x, frame.origin.y)


class ConfidencePanelController:
    """Manages the confidence/quality floating panel."""

    def __init__(self, settings, on_position_changed=None):
        self.settings = settings
        self.on_position_changed = on_position_changed
        self._setup_window()

    def _setup_window(self):
        """Create the floating panel window with vibrancy."""
        x = self.settings.confidence_panel_x
        y = self.settings.confidence_panel_y
        frame = NSMakeRect(x, y, PANEL_WIDTH, PANEL_HEIGHT)

        self.window = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            frame,
            NSWindowStyleMaskBorderless,
            NSBackingStoreBuffered,
            False,
        )
        self.window.setLevel_(NSFloatingWindowLevel)
        self.window.setBackgroundColor_(NSColor.clearColor())
        self.window.setOpaque_(False)
        self.window.setHasShadow_(True)
        self.window.setMovableByWindowBackground_(False)
        self.window.setIgnoresMouseEvents_(False)

        # Visual effect (blur) background
        effect_view = NSVisualEffectView.alloc().initWithFrame_(
            NSMakeRect(0, 0, PANEL_WIDTH, PANEL_HEIGHT)
        )
        effect_view.setMaterial_(NSVisualEffectMaterialDark)
        effect_view.setBlendingMode_(NSVisualEffectBlendingModeBehindWindow)
        effect_view.setState_(AppKit.NSVisualEffectStateActive)
        effect_view.setWantsLayer_(True)
        effect_view.layer().setCornerRadius_(12)
        effect_view.layer().setMasksToBounds_(True)
        self.window.setContentView_(effect_view)

        # Content view on top of effect view
        self.view = ConfidencePanelView.alloc().initWithFrame_(
            NSMakeRect(0, 0, PANEL_WIDTH, PANEL_HEIGHT)
        )
        self.view._show_fps = self.settings.show_fps
        self.view._on_position_changed = self.on_position_changed
        effect_view.addSubview_(self.view)

    def show(self):
        self.window.orderFront_(None)

    def hide(self):
        self.window.orderOut_(None)

    def update(self, status, confidence, fps):
        """Update the panel with current tracking state.

        Args:
            status: "tracking", "low_confidence", or "face_lost"
            confidence: float 0-1
            fps: float
        """
        if status == "tracking":
            self.view._status = "Tracking"
            self.view._status_color = NSColor.colorWithCalibratedRed_green_blue_alpha_(0.2, 0.8, 0.3, 1.0)
        elif status == "low_confidence":
            self.view._status = "Low confidence"
            self.view._status_color = NSColor.colorWithCalibratedRed_green_blue_alpha_(0.9, 0.7, 0.1, 1.0)
        else:
            self.view._status = "Face not detected"
            self.view._status_color = NSColor.colorWithCalibratedRed_green_blue_alpha_(0.9, 0.2, 0.2, 1.0)

        self.view._confidence = confidence
        self.view._fps = fps
        self.view._show_fps = self.settings.show_fps
        self.view.setNeedsDisplay_(True)

    def update_settings(self, settings):
        self.settings = settings
        self.view._show_fps = settings.show_fps
        self.view.setNeedsDisplay_(True)
