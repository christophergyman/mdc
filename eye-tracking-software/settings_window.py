"""Settings UI window — native macOS preferences panel with sectioned layout."""

import objc
import AppKit
from Foundation import NSObject, NSMakeRect, NSMakeSize
from AppKit import (
    NSWindow, NSView, NSColor, NSFont, NSScreen,
    NSWindowStyleMaskTitled, NSWindowStyleMaskClosable,
    NSBackingStoreBuffered, NSTextField, NSSlider,
    NSButton, NSColorWell, NSSwitchButton, NSPopUpButton,
    NSFloatingWindowLevel, NSScrollView, NSBox,
    NSBoxSeparator,
)
import AVFoundation


def _enumerate_cameras():
    """Return list of (index, name) for connected video capture devices.

    Uses AVFoundation discovery session.  Device order matches OpenCV index
    order on macOS (both enumerate via the same AVFoundation backend).
    """
    device_types = [AVFoundation.AVCaptureDeviceTypeBuiltInWideAngleCamera]
    # Try external/USB camera type (available macOS 14+)
    try:
        device_types.append(AVFoundation.AVCaptureDeviceTypeExternal)
    except AttributeError:
        pass

    session = (
        AVFoundation.AVCaptureDeviceDiscoverySession
        .discoverySessionWithDeviceTypes_mediaType_position_(
            device_types,
            AVFoundation.AVMediaTypeVideo,
            AVFoundation.AVCaptureDevicePositionUnspecified,
        )
    )
    devices = session.devices() if session else []
    return [(i, str(d.localizedName())) for i, d in enumerate(devices)]


# Resolution and FPS presets
_RESOLUTION_PRESETS = [
    (640, 480, "640 × 480"),
    (1280, 720, "1280 × 720"),
    (1920, 1080, "1920 × 1080"),
]

_FPS_PRESETS = [15, 30, 60]


class SettingsWindowController:
    """Native macOS settings/preferences window with sectioned layout."""

    def __init__(self, settings, on_settings_changed=None):
        self.settings = settings
        self.on_settings_changed = on_settings_changed
        self._cameras = []
        self._setup_window()

    # ------------------------------------------------------------------
    # Window construction
    # ------------------------------------------------------------------

    def _setup_window(self):
        """Create the settings window with scrollable sectioned content."""
        win_w, win_h = 480, 560
        screen = NSScreen.mainScreen().frame()
        x = (screen.size.width - win_w) / 2
        y = (screen.size.height - win_h) / 2

        self.window = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            NSMakeRect(x, y, win_w, win_h),
            NSWindowStyleMaskTitled | NSWindowStyleMaskClosable,
            NSBackingStoreBuffered,
            False,
        )
        self.window.setTitle_("GazeTracker Settings")
        self.window.setLevel_(NSFloatingWindowLevel)
        self.window.setReleasedWhenClosed_(False)

        # Scroll view wrapping the content
        scroll = NSScrollView.alloc().initWithFrame_(
            NSMakeRect(0, 0, win_w, win_h)
        )
        scroll.setHasVerticalScrollbar_(True)
        scroll.setAutohidesScrollers_(True)

        # Inner document view — tall enough for all sections
        content_h = 680
        content = NSView.alloc().initWithFrame_(
            NSMakeRect(0, 0, win_w, content_h)
        )
        content.setFlipped_(True)

        pad_x = 24
        label_w = 160
        ctrl_x = pad_x + label_w + 8
        ctrl_w = 180
        y_pos = 16  # flipped: top = small number

        # ========== Section 1: Camera ==========
        y_pos = self._add_section_header(content, "Camera", pad_x, y_pos)

        # Camera Device
        y_pos = self._add_label(content, "Camera Device:", pad_x, y_pos)
        self._camera_popup = NSPopUpButton.alloc().initWithFrame_pullsDown_(
            NSMakeRect(ctrl_x, y_pos - 2, ctrl_w, 24), False
        )
        content.addSubview_(self._camera_popup)
        self._refresh_btn = NSButton.alloc().initWithFrame_(
            NSMakeRect(ctrl_x + ctrl_w + 6, y_pos - 2, 70, 24)
        )
        self._refresh_btn.setTitle_("Refresh")
        self._refresh_btn.setBezelStyle_(AppKit.NSBezelStyleRounded)
        self._refresh_btn.setTarget_(self)
        self._refresh_btn.setAction_(objc.selector(self._on_refresh_cameras, signature=b"v@:@"))
        content.addSubview_(self._refresh_btn)
        self._populate_camera_popup()
        self._camera_popup.setTarget_(self)
        self._camera_popup.setAction_(objc.selector(self._on_camera_changed, signature=b"v@:@"))
        y_pos += 34

        # Resolution
        y_pos = self._add_label(content, "Resolution:", pad_x, y_pos)
        self._resolution_popup = NSPopUpButton.alloc().initWithFrame_pullsDown_(
            NSMakeRect(ctrl_x, y_pos - 2, ctrl_w, 24), False
        )
        for w, h, title in _RESOLUTION_PRESETS:
            self._resolution_popup.addItemWithTitle_(title)
        # Select current
        cur_res = (self.settings.camera_resolution_w, self.settings.camera_resolution_h)
        for idx, (w, h, _) in enumerate(_RESOLUTION_PRESETS):
            if (w, h) == cur_res:
                self._resolution_popup.selectItemAtIndex_(idx)
                break
        self._resolution_popup.setTarget_(self)
        self._resolution_popup.setAction_(objc.selector(self._on_resolution_changed, signature=b"v@:@"))
        content.addSubview_(self._resolution_popup)
        y_pos += 34

        # Frame Rate
        y_pos = self._add_label(content, "Frame Rate:", pad_x, y_pos)
        self._fps_popup = NSPopUpButton.alloc().initWithFrame_pullsDown_(
            NSMakeRect(ctrl_x, y_pos - 2, ctrl_w, 24), False
        )
        for fps in _FPS_PRESETS:
            self._fps_popup.addItemWithTitle_(f"{fps} fps")
        cur_fps = self.settings.camera_fps
        for idx, fps in enumerate(_FPS_PRESETS):
            if fps == cur_fps:
                self._fps_popup.selectItemAtIndex_(idx)
                break
        self._fps_popup.setTarget_(self)
        self._fps_popup.setAction_(objc.selector(self._on_fps_changed, signature=b"v@:@"))
        content.addSubview_(self._fps_popup)
        y_pos += 40

        # ========== Section 2: Tracking ==========
        y_pos = self._add_section_header(content, "Tracking", pad_x, y_pos)

        # Smoothing
        y_pos = self._add_label(content, "Smoothing:", pad_x, y_pos)
        self._smooth_slider = NSSlider.alloc().initWithFrame_(
            NSMakeRect(ctrl_x, y_pos, ctrl_w, 20)
        )
        self._smooth_slider.setMinValue_(0.05)
        self._smooth_slider.setMaxValue_(0.95)
        self._smooth_slider.setFloatValue_(self.settings.smoothing_alpha)
        self._smooth_slider.setTarget_(self)
        self._smooth_slider.setAction_(objc.selector(self._on_smooth_changed, signature=b"v@:@"))
        content.addSubview_(self._smooth_slider)
        self._smooth_label = self._add_value_label(
            content, f"{self.settings.smoothing_alpha:.2f}", ctrl_x + ctrl_w + 8, y_pos
        )
        y_pos += 30

        # Smoothing hint
        hint = NSTextField.alloc().initWithFrame_(NSMakeRect(ctrl_x, y_pos, ctrl_w + 80, 16))
        hint.setStringValue_("Lower = smoother, higher = more reactive")
        hint.setEditable_(False)
        hint.setBezeled_(False)
        hint.setDrawsBackground_(False)
        hint.setTextColor_(NSColor.secondaryLabelColor())
        hint.setFont_(NSFont.systemFontOfSize_(10))
        content.addSubview_(hint)
        y_pos += 24

        # Auto-recalibrate prompt
        y_pos = self._add_label(content, "Auto-recalibrate:", pad_x, y_pos)
        self._auto_recal_toggle = NSButton.alloc().initWithFrame_(
            NSMakeRect(ctrl_x, y_pos - 2, 200, 20)
        )
        self._auto_recal_toggle.setButtonType_(NSSwitchButton)
        self._auto_recal_toggle.setTitle_("Prompt when confidence low")
        self._auto_recal_toggle.setFont_(NSFont.systemFontOfSize_(11))
        self._auto_recal_toggle.setState_(1 if self.settings.auto_recalibrate_prompt else 0)
        self._auto_recal_toggle.setTarget_(self)
        self._auto_recal_toggle.setAction_(objc.selector(self._on_auto_recal_toggled, signature=b"v@:@"))
        content.addSubview_(self._auto_recal_toggle)
        y_pos += 40

        # ========== Section 3: Crosshair ==========
        y_pos = self._add_section_header(content, "Crosshair", pad_x, y_pos)

        # Colour
        y_pos = self._add_label(content, "Colour:", pad_x, y_pos)
        self._color_well = NSColorWell.alloc().initWithFrame_(
            NSMakeRect(ctrl_x, y_pos - 2, 44, 24)
        )
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
        y_pos += 34

        # Size
        y_pos = self._add_label(content, "Size:", pad_x, y_pos)
        self._size_slider = NSSlider.alloc().initWithFrame_(
            NSMakeRect(ctrl_x, y_pos, ctrl_w, 20)
        )
        self._size_slider.setMinValue_(10)
        self._size_slider.setMaxValue_(80)
        self._size_slider.setIntValue_(self.settings.crosshair_size)
        self._size_slider.setTarget_(self)
        self._size_slider.setAction_(objc.selector(self._on_size_changed, signature=b"v@:@"))
        content.addSubview_(self._size_slider)
        self._size_label = self._add_value_label(
            content, f"{self.settings.crosshair_size}px", ctrl_x + ctrl_w + 8, y_pos
        )
        y_pos += 30

        # Line Width
        y_pos = self._add_label(content, "Line Width:", pad_x, y_pos)
        self._line_width_slider = NSSlider.alloc().initWithFrame_(
            NSMakeRect(ctrl_x, y_pos, ctrl_w, 20)
        )
        self._line_width_slider.setMinValue_(0.5)
        self._line_width_slider.setMaxValue_(4.0)
        self._line_width_slider.setFloatValue_(self.settings.crosshair_line_width)
        self._line_width_slider.setTarget_(self)
        self._line_width_slider.setAction_(objc.selector(self._on_line_width_changed, signature=b"v@:@"))
        content.addSubview_(self._line_width_slider)
        self._line_width_label = self._add_value_label(
            content, f"{self.settings.crosshair_line_width:.1f}", ctrl_x + ctrl_w + 8, y_pos
        )
        y_pos += 30

        # Centre Gap
        y_pos = self._add_label(content, "Centre Gap:", pad_x, y_pos)
        self._gap_slider = NSSlider.alloc().initWithFrame_(
            NSMakeRect(ctrl_x, y_pos, ctrl_w, 20)
        )
        self._gap_slider.setMinValue_(0)
        self._gap_slider.setMaxValue_(20)
        self._gap_slider.setIntValue_(self.settings.crosshair_gap)
        self._gap_slider.setTarget_(self)
        self._gap_slider.setAction_(objc.selector(self._on_gap_changed, signature=b"v@:@"))
        content.addSubview_(self._gap_slider)
        self._gap_label = self._add_value_label(
            content, f"{self.settings.crosshair_gap}px", ctrl_x + ctrl_w + 8, y_pos
        )
        y_pos += 40

        # ========== Section 4: Display ==========
        y_pos = self._add_section_header(content, "Display", pad_x, y_pos)

        # Show Webcam Preview
        y_pos = self._add_label(content, "Webcam Preview:", pad_x, y_pos)
        self._webcam_toggle = NSButton.alloc().initWithFrame_(
            NSMakeRect(ctrl_x, y_pos - 2, 40, 20)
        )
        self._webcam_toggle.setButtonType_(NSSwitchButton)
        self._webcam_toggle.setTitle_("")
        self._webcam_toggle.setState_(1 if self.settings.show_webcam_preview else 0)
        self._webcam_toggle.setTarget_(self)
        self._webcam_toggle.setAction_(objc.selector(self._on_webcam_toggled, signature=b"v@:@"))
        content.addSubview_(self._webcam_toggle)
        y_pos += 30

        # Show FPS
        y_pos = self._add_label(content, "Show FPS in Panel:", pad_x, y_pos)
        self._fps_toggle = NSButton.alloc().initWithFrame_(
            NSMakeRect(ctrl_x, y_pos - 2, 40, 20)
        )
        self._fps_toggle.setButtonType_(NSSwitchButton)
        self._fps_toggle.setTitle_("")
        self._fps_toggle.setState_(1 if self.settings.show_fps else 0)
        self._fps_toggle.setTarget_(self)
        self._fps_toggle.setAction_(objc.selector(self._on_fps_toggled, signature=b"v@:@"))
        content.addSubview_(self._fps_toggle)
        y_pos += 30

        # Show/Hide Hotkey (read-only)
        y_pos = self._add_label(content, "Show/Hide Hotkey:", pad_x, y_pos)
        self._hotkey_field = NSTextField.alloc().initWithFrame_(
            NSMakeRect(ctrl_x, y_pos - 2, ctrl_w, 24)
        )
        self._hotkey_field.setStringValue_(self.settings.hotkey_display)
        self._hotkey_field.setEditable_(False)
        self._hotkey_field.setBezeled_(True)
        self._hotkey_field.setAlignment_(AppKit.NSTextAlignmentCenter)
        content.addSubview_(self._hotkey_field)
        y_pos += 40

        # Resize document view to fit content
        content.setFrameSize_(NSMakeSize(win_w, max(y_pos + 16, win_h)))
        scroll.setDocumentView_(content)
        self.window.setContentView_(scroll)

    # ------------------------------------------------------------------
    # Helpers — layout
    # ------------------------------------------------------------------

    def _add_section_header(self, parent, title, x, y):
        """Add a bold section header + separator line. Returns updated y."""
        label = NSTextField.alloc().initWithFrame_(NSMakeRect(x, y, 300, 20))
        label.setStringValue_(title)
        label.setEditable_(False)
        label.setBezeled_(False)
        label.setDrawsBackground_(False)
        label.setFont_(NSFont.boldSystemFontOfSize_(13))
        parent.addSubview_(label)
        y += 22

        sep = NSBox.alloc().initWithFrame_(NSMakeRect(x, y, 432, 1))
        sep.setBoxType_(NSBoxSeparator)
        parent.addSubview_(sep)
        y += 10
        return y

    def _add_label(self, parent, text, x, y):
        """Add a standard label at (x, y). Returns y unchanged."""
        label = NSTextField.alloc().initWithFrame_(NSMakeRect(x, y, 160, 20))
        label.setStringValue_(text)
        label.setEditable_(False)
        label.setBezeled_(False)
        label.setDrawsBackground_(False)
        label.setFont_(NSFont.systemFontOfSize_(13))
        parent.addSubview_(label)
        return y

    def _add_value_label(self, parent, text, x, y):
        """Small value label next to sliders."""
        label = NSTextField.alloc().initWithFrame_(NSMakeRect(x, y, 50, 20))
        label.setStringValue_(text)
        label.setEditable_(False)
        label.setBezeled_(False)
        label.setDrawsBackground_(False)
        label.setFont_(NSFont.systemFontOfSize_(11))
        label.setTextColor_(NSColor.secondaryLabelColor())
        parent.addSubview_(label)
        return label

    # ------------------------------------------------------------------
    # Camera enumeration
    # ------------------------------------------------------------------

    def _populate_camera_popup(self):
        """Enumerate cameras and populate the popup button."""
        self._cameras = _enumerate_cameras()
        self._camera_popup.removeAllItems()

        if not self._cameras:
            self._camera_popup.addItemWithTitle_("No cameras found")
            return

        selected_idx = 0
        for i, (dev_idx, name) in enumerate(self._cameras):
            self._camera_popup.addItemWithTitle_(name)
            # Match by name first (handles index shifts), fall back to index
            if self.settings.camera_device_name and name == self.settings.camera_device_name:
                selected_idx = i
            elif not self.settings.camera_device_name and dev_idx == self.settings.camera_device_index:
                selected_idx = i

        self._camera_popup.selectItemAtIndex_(selected_idx)

    # ------------------------------------------------------------------
    # Callbacks — Camera section
    # ------------------------------------------------------------------

    def _on_refresh_cameras(self, sender):
        self._populate_camera_popup()

    def _on_camera_changed(self, sender):
        idx = self._camera_popup.indexOfSelectedItem()
        if 0 <= idx < len(self._cameras):
            dev_idx, name = self._cameras[idx]
            self.settings.camera_device_index = dev_idx
            self.settings.camera_device_name = name
            self._notify()

    def _on_resolution_changed(self, sender):
        idx = self._resolution_popup.indexOfSelectedItem()
        if 0 <= idx < len(_RESOLUTION_PRESETS):
            w, h, _ = _RESOLUTION_PRESETS[idx]
            self.settings.camera_resolution_w = w
            self.settings.camera_resolution_h = h
            self._notify()

    def _on_fps_changed(self, sender):
        idx = self._fps_popup.indexOfSelectedItem()
        if 0 <= idx < len(_FPS_PRESETS):
            self.settings.camera_fps = _FPS_PRESETS[idx]
            self._notify()

    # ------------------------------------------------------------------
    # Callbacks — Tracking section
    # ------------------------------------------------------------------

    def _on_smooth_changed(self, sender):
        val = round(self._smooth_slider.floatValue(), 2)
        self.settings.smoothing_alpha = val
        self._smooth_label.setStringValue_(f"{val:.2f}")
        self._notify()

    def _on_auto_recal_toggled(self, sender):
        self.settings.auto_recalibrate_prompt = bool(self._auto_recal_toggle.state())
        self._notify()

    # ------------------------------------------------------------------
    # Callbacks — Crosshair section
    # ------------------------------------------------------------------

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

    def _on_line_width_changed(self, sender):
        val = round(self._line_width_slider.floatValue(), 1)
        self.settings.crosshair_line_width = val
        self._line_width_label.setStringValue_(f"{val:.1f}")
        self._notify()

    def _on_gap_changed(self, sender):
        val = int(self._gap_slider.intValue())
        self.settings.crosshair_gap = val
        self._gap_label.setStringValue_(f"{val}px")
        self._notify()

    # ------------------------------------------------------------------
    # Callbacks — Display section
    # ------------------------------------------------------------------

    def _on_webcam_toggled(self, sender):
        self.settings.show_webcam_preview = bool(self._webcam_toggle.state())
        self._notify()

    def _on_fps_toggled(self, sender):
        self.settings.show_fps = bool(self._fps_toggle.state())
        self._notify()

    # ------------------------------------------------------------------
    # Notify & window control
    # ------------------------------------------------------------------

    def _notify(self):
        self.settings.save()
        if self.on_settings_changed:
            self.on_settings_changed(self.settings)

    def show(self):
        self.window.makeKeyAndOrderFront_(None)

    def hide(self):
        self.window.orderOut_(None)
