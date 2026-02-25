"""Settings UI window — native macOS preferences panel."""

import objc
import AppKit
from Foundation import NSObject, NSMakeRect
from AppKit import (
    NSWindow, NSView, NSColor, NSFont, NSScreen,
    NSWindowStyleMaskTitled, NSWindowStyleMaskClosable,
    NSBackingStoreBuffered, NSTextField, NSSlider,
    NSButton, NSColorWell, NSSwitchButton,
    NSFloatingWindowLevel, NSStackView,
    NSUserInterfaceLayoutOrientationVertical,
)


class SettingsWindowController:
    """Native macOS settings/preferences window."""

    def __init__(self, settings, on_settings_changed=None):
        self.settings = settings
        self.on_settings_changed = on_settings_changed
        self._setup_window()

    def _setup_window(self):
        """Create the settings window with controls."""
        width = 400
        height = 380
        screen = NSScreen.mainScreen().frame()
        x = (screen.size.width - width) / 2
        y = (screen.size.height - height) / 2
        frame = NSMakeRect(x, y, width, height)

        self.window = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            frame,
            NSWindowStyleMaskTitled | NSWindowStyleMaskClosable,
            NSBackingStoreBuffered,
            False,
        )
        self.window.setTitle_("GazeTracker Settings")
        self.window.setLevel_(NSFloatingWindowLevel)
        self.window.setReleasedWhenClosed_(False)

        content = self.window.contentView()
        y_pos = height - 50

        # --- Crosshair Colour ---
        y_pos = self._add_label(content, "Crosshair Colour:", 20, y_pos)
        self._color_well = NSColorWell.alloc().initWithFrame_(NSMakeRect(200, y_pos + 2, 44, 24))
        self._color_well.setColor_(
            NSColor.colorWithCalibratedRed_green_blue_alpha_(
                self.settings.crosshair_color_r,
                self.settings.crosshair_color_g,
                self.settings.crosshair_color_b,
                self.settings.crosshair_color_a,
            )
        )
        self._color_well.setTarget_(self)
        self._color_well.setAction_(objc.selector(self._on_color_changed, signature=b"v@:@"))
        content.addSubview_(self._color_well)
        y_pos -= 40

        # --- Crosshair Size ---
        y_pos = self._add_label(content, "Crosshair Size:", 20, y_pos)
        self._size_slider = NSSlider.alloc().initWithFrame_(NSMakeRect(200, y_pos + 4, 160, 20))
        self._size_slider.setMinValue_(10)
        self._size_slider.setMaxValue_(80)
        self._size_slider.setIntValue_(self.settings.crosshair_size)
        self._size_slider.setTarget_(self)
        self._size_slider.setAction_(objc.selector(self._on_size_changed, signature=b"v@:@"))
        content.addSubview_(self._size_slider)
        self._size_label = self._add_value_label(content, f"{self.settings.crosshair_size}px", 365, y_pos)
        y_pos -= 40

        # --- Smoothing ---
        y_pos = self._add_label(content, "Smoothing:", 20, y_pos)
        self._smooth_slider = NSSlider.alloc().initWithFrame_(NSMakeRect(200, y_pos + 4, 160, 20))
        self._smooth_slider.setMinValue_(0.1)
        self._smooth_slider.setMaxValue_(0.9)
        self._smooth_slider.setFloatValue_(self.settings.smoothing_alpha)
        self._smooth_slider.setTarget_(self)
        self._smooth_slider.setAction_(objc.selector(self._on_smooth_changed, signature=b"v@:@"))
        content.addSubview_(self._smooth_slider)
        self._smooth_label = self._add_value_label(content, f"{self.settings.smoothing_alpha:.2f}", 365, y_pos)
        y_pos -= 40

        # --- Hotkey ---
        y_pos = self._add_label(content, "Show/Hide Hotkey:", 20, y_pos)
        self._hotkey_label = NSTextField.alloc().initWithFrame_(NSMakeRect(200, y_pos + 2, 160, 24))
        self._hotkey_label.setStringValue_(self.settings.hotkey_display)
        self._hotkey_label.setEditable_(False)
        self._hotkey_label.setBezeled_(True)
        self._hotkey_label.setAlignment_(AppKit.NSTextAlignmentCenter)
        content.addSubview_(self._hotkey_label)
        y_pos -= 40

        # --- Show Webcam Preview ---
        y_pos = self._add_label(content, "Show Webcam Preview:", 20, y_pos)
        self._webcam_toggle = NSButton.alloc().initWithFrame_(NSMakeRect(200, y_pos + 2, 40, 24))
        self._webcam_toggle.setButtonType_(NSSwitchButton)
        self._webcam_toggle.setTitle_("")
        self._webcam_toggle.setState_(1 if self.settings.show_webcam_preview else 0)
        self._webcam_toggle.setTarget_(self)
        self._webcam_toggle.setAction_(objc.selector(self._on_webcam_toggled, signature=b"v@:@"))
        content.addSubview_(self._webcam_toggle)
        y_pos -= 40

        # --- Show FPS ---
        y_pos = self._add_label(content, "Show FPS in Panel:", 20, y_pos)
        self._fps_toggle = NSButton.alloc().initWithFrame_(NSMakeRect(200, y_pos + 2, 40, 24))
        self._fps_toggle.setButtonType_(NSSwitchButton)
        self._fps_toggle.setTitle_("")
        self._fps_toggle.setState_(1 if self.settings.show_fps else 0)
        self._fps_toggle.setTarget_(self)
        self._fps_toggle.setAction_(objc.selector(self._on_fps_toggled, signature=b"v@:@"))
        content.addSubview_(self._fps_toggle)
        y_pos -= 50

        # --- Info text ---
        info = NSTextField.alloc().initWithFrame_(NSMakeRect(20, y_pos, 360, 30))
        info.setStringValue_("Smoothing: lower = smoother/calmer, higher = more reactive")
        info.setEditable_(False)
        info.setBezeled_(False)
        info.setDrawsBackground_(False)
        info.setTextColor_(NSColor.secondaryLabelColor())
        info.setFont_(NSFont.systemFontOfSize_(11))
        content.addSubview_(info)

    def _add_label(self, parent, text, x, y):
        """Add a label at the given position, return y for alignment."""
        label = NSTextField.alloc().initWithFrame_(NSMakeRect(x, y, 180, 20))
        label.setStringValue_(text)
        label.setEditable_(False)
        label.setBezeled_(False)
        label.setDrawsBackground_(False)
        label.setFont_(NSFont.systemFontOfSize_(13))
        parent.addSubview_(label)
        return y

    def _add_value_label(self, parent, text, x, y):
        """Add a small value label (for showing slider values)."""
        label = NSTextField.alloc().initWithFrame_(NSMakeRect(x, y + 4, 40, 20))
        label.setStringValue_(text)
        label.setEditable_(False)
        label.setBezeled_(False)
        label.setDrawsBackground_(False)
        label.setFont_(NSFont.systemFontOfSize_(11))
        label.setTextColor_(NSColor.secondaryLabelColor())
        parent.addSubview_(label)
        return label

    def _on_color_changed(self, sender):
        color = self._color_well.color()
        self.settings.crosshair_color_r = color.redComponent()
        self.settings.crosshair_color_g = color.greenComponent()
        self.settings.crosshair_color_b = color.blueComponent()
        self.settings.crosshair_color_a = color.alphaComponent()
        self._notify()

    def _on_size_changed(self, sender):
        val = int(self._size_slider.intValue())
        self.settings.crosshair_size = val
        self._size_label.setStringValue_(f"{val}px")
        self._notify()

    def _on_smooth_changed(self, sender):
        val = round(self._smooth_slider.floatValue(), 2)
        self.settings.smoothing_alpha = val
        self._smooth_label.setStringValue_(f"{val:.2f}")
        self._notify()

    def _on_webcam_toggled(self, sender):
        self.settings.show_webcam_preview = bool(self._webcam_toggle.state())
        self._notify()

    def _on_fps_toggled(self, sender):
        self.settings.show_fps = bool(self._fps_toggle.state())
        self._notify()

    def _notify(self):
        self.settings.save()
        if self.on_settings_changed:
            self.on_settings_changed(self.settings)

    def show(self):
        self.window.makeKeyAndOrderFront_(None)

    def hide(self):
        self.window.orderOut_(None)
