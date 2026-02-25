"""GazeTracker — main application entry point and lifecycle management."""

import sys
import time
import threading
import cv2
import objc
import AppKit
from Foundation import NSObject, NSTimer, NSRunLoop, NSDefaultRunLoopMode, NSMakeRect
from AppKit import (
    NSApplication, NSMenu, NSMenuItem, NSScreen, NSWindow, NSAlert,
    NSAlertStyleCritical, NSAlertStyleWarning, NSStatusBar,
    NSImage, NSColor, NSFont, NSTextField,
    NSWindowStyleMaskBorderless, NSBackingStoreBuffered,
)

from settings import Settings
from gaze_estimator import GazeEstimator
from calibration import CalibrationController
from overlay import OverlayController
from confidence_panel import ConfidencePanelController
from settings_window import SettingsWindowController
from webcam_preview import WebcamPreviewController


class AppDelegate(NSObject):
    """Main application delegate — manages lifecycle and coordinates all components."""

    def init(self):
        self = objc.super(AppDelegate, self).init()
        if self is None:
            return None

        self.settings = Settings.load()
        self.estimator = GazeEstimator()
        self.capture = None
        self.overlay = None
        self.confidence_panel = None
        self.settings_window = None
        self.webcam_preview = None
        self.calibration = None
        self.tracking_timer = None
        self.is_tracking = False

        # FPS tracking
        self._frame_times = []
        self._current_fps = 0.0

        return self

    def applicationDidFinishLaunching_(self, notification):
        """App has launched — set up menus and start the pipeline."""
        self._setup_menus()

        # Check camera permission and start
        if not self._open_camera():
            return

        # Start calibration
        self._start_calibration()

    def applicationWillTerminate_(self, notification):
        """Clean up on quit."""
        self._stop_tracking()
        if self.capture:
            self.capture.release()
        self.estimator.close()
        self.settings.save()

    def applicationShouldTerminateAfterLastWindowClosed_(self, app):
        return False

    # --- Menu Setup ---

    def _setup_menus(self):
        """Create the app menu bar."""
        menubar = NSMenu.alloc().init()

        # App menu
        app_menu = NSMenu.alloc().initWithTitle_("GazeTracker")
        app_menu.addItemWithTitle_action_keyEquivalent_("About GazeTracker", "showAbout:", "")
        app_menu.addItem_(NSMenuItem.separatorItem())
        app_menu.addItemWithTitle_action_keyEquivalent_("Settings...", "showSettings:", ",")
        app_menu.addItem_(NSMenuItem.separatorItem())
        quit_item = app_menu.addItemWithTitle_action_keyEquivalent_("Quit GazeTracker", "terminate:", "q")

        app_menu_item = NSMenuItem.alloc().init()
        app_menu_item.setSubmenu_(app_menu)
        menubar.addItem_(app_menu_item)

        # Tracking menu
        tracking_menu = NSMenu.alloc().initWithTitle_("Tracking")
        tracking_menu.addItemWithTitle_action_keyEquivalent_("Start Calibration", "startCalibration:", "r")
        tracking_menu.addItem_(NSMenuItem.separatorItem())
        tracking_menu.addItemWithTitle_action_keyEquivalent_("Show/Hide Overlay", "toggleOverlay:", "g")
        tracking_menu.addItemWithTitle_action_keyEquivalent_("Show Webcam Preview", "toggleWebcamPreview:", "w")

        tracking_menu_item = NSMenuItem.alloc().init()
        tracking_menu_item.setSubmenu_(tracking_menu)
        menubar.addItem_(tracking_menu_item)

        NSApplication.sharedApplication().setMainMenu_(menubar)

    # --- Camera ---

    def _open_camera(self):
        """Open the webcam using current settings. Returns True on success."""
        device_index = self.settings.camera_device_index
        self.capture = cv2.VideoCapture(device_index)
        if not self.capture.isOpened():
            self._show_camera_error()
            return False

        # Apply resolution and frame rate from settings
        self.capture.set(cv2.CAP_PROP_FRAME_WIDTH, self.settings.camera_resolution_w)
        self.capture.set(cv2.CAP_PROP_FRAME_HEIGHT, self.settings.camera_resolution_h)
        self.capture.set(cv2.CAP_PROP_FPS, self.settings.camera_fps)
        return True

    def _switch_camera(self):
        """Switch to a different camera or apply new resolution/fps.

        Stops tracking, releases the old capture, opens the new device,
        and triggers recalibration (different camera = different FOV).
        """
        was_tracking = self.is_tracking
        self._stop_tracking()

        if self.capture:
            self.capture.release()
            self.capture = None

        if not self._open_camera():
            return

        # Different camera or resolution invalidates calibration
        if was_tracking:
            self._start_calibration()

    def _show_camera_error(self):
        """Show camera access error dialog."""
        alert = NSAlert.alloc().init()
        alert.setAlertStyle_(NSAlertStyleCritical)
        alert.setMessageText_("Camera Access Required")
        alert.setInformativeText_(
            "GazeTracker needs camera access to track your gaze.\n\n"
            "Please grant camera access in System Settings > Privacy & Security > Camera."
        )
        alert.addButtonWithTitle_("Open System Settings")
        alert.addButtonWithTitle_("Quit")

        response = alert.runModal()
        if response == AppKit.NSAlertFirstButtonReturn:
            import subprocess
            subprocess.Popen(["open", "x-apple.systempreferences:com.apple.preference.security?Privacy_Camera"])
        NSApplication.sharedApplication().terminate_(None)

    # --- Calibration ---

    def _start_calibration(self):
        """Start the calibration routine."""
        self._stop_tracking()

        if self.overlay:
            self.overlay.hide()
        if self.confidence_panel:
            self.confidence_panel.hide()

        self.calibration = CalibrationController(
            gaze_estimator=self.estimator,
            webcam_capture=self.capture,
            on_complete=self._on_calibration_complete,
        )
        self.calibration.start()

    def _on_calibration_complete(self, success):
        """Called when calibration finishes."""
        self.calibration = None
        if success:
            self._start_tracking()
        else:
            # Offer to retry
            alert = NSAlert.alloc().init()
            alert.setAlertStyle_(NSAlertStyleWarning)
            alert.setMessageText_("Calibration Failed")
            alert.setInformativeText_("Would you like to try again?")
            alert.addButtonWithTitle_("Retry")
            alert.addButtonWithTitle_("Quit")
            response = alert.runModal()
            if response == AppKit.NSAlertFirstButtonReturn:
                self._start_calibration()
            else:
                NSApplication.sharedApplication().terminate_(None)

    # --- Tracking ---

    def _start_tracking(self):
        """Start the gaze tracking loop."""
        if self.overlay is None:
            self.overlay = OverlayController(self.settings)
        self.overlay.show()

        if self.confidence_panel is None:
            self.confidence_panel = ConfidencePanelController(
                self.settings,
                on_position_changed=self._on_panel_position_changed,
            )
        self.confidence_panel.show()

        if self.settings.show_webcam_preview:
            self._show_webcam_preview()

        self.is_tracking = True

        # Start tracking timer on main thread (30fps)
        self.tracking_timer = NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
            1.0 / 30.0, self, "trackingTick:", None, True
        )
        NSRunLoop.currentRunLoop().addTimer_forMode_(self.tracking_timer, NSDefaultRunLoopMode)

        # Set up global hotkey monitor
        self._hotkey_monitor = AppKit.NSEvent.addGlobalMonitorForEventsMatchingMask_handler_(
            AppKit.NSEventMaskKeyDown,
            self._handle_global_hotkey,
        )
        self._local_hotkey_monitor = AppKit.NSEvent.addLocalMonitorForEventsMatchingMask_handler_(
            AppKit.NSEventMaskKeyDown,
            self._handle_local_hotkey,
        )

    def _stop_tracking(self):
        """Stop the tracking loop."""
        self.is_tracking = False
        if self.tracking_timer:
            self.tracking_timer.invalidate()
            self.tracking_timer = None
        if hasattr(self, '_hotkey_monitor') and self._hotkey_monitor:
            AppKit.NSEvent.removeMonitor_(self._hotkey_monitor)
            self._hotkey_monitor = None
        if hasattr(self, '_local_hotkey_monitor') and self._local_hotkey_monitor:
            AppKit.NSEvent.removeMonitor_(self._local_hotkey_monitor)
            self._local_hotkey_monitor = None

    def trackingTick_(self, timer):
        """Main tracking loop — called ~30fps on the main thread."""
        if not self.is_tracking or self.capture is None:
            return

        frame_start = time.time()

        ret, frame = self.capture.read()
        if not ret:
            return

        features, confidence, face_landmarks = self.estimator.process_frame(frame)

        if features is not None:
            prediction = self.estimator.predict(features)
            if prediction:
                raw_x, raw_y = prediction
                face_detected = True
            else:
                raw_x, raw_y = 0, 0
                face_detected = False
                confidence = 0.0
        else:
            raw_x, raw_y = 0, 0
            face_detected = False
            confidence = 0.0

        # Update overlay
        if self.overlay:
            self.overlay.update_gaze(raw_x, raw_y, face_detected, confidence)

        # Update confidence panel
        if self.confidence_panel:
            if not face_detected:
                status = "face_lost"
            elif confidence < 0.4:
                status = "low_confidence"
            else:
                status = "tracking"
            self.confidence_panel.update(status, confidence, self._current_fps)

        # Update webcam preview
        if self.webcam_preview and self.webcam_preview.is_visible():
            self.webcam_preview.update_frame(frame, face_landmarks)

        # FPS calculation
        frame_end = time.time()
        self._frame_times.append(frame_end)
        # Keep last 30 frame times
        self._frame_times = self._frame_times[-30:]
        if len(self._frame_times) >= 2:
            elapsed = self._frame_times[-1] - self._frame_times[0]
            if elapsed > 0:
                self._current_fps = (len(self._frame_times) - 1) / elapsed

    # --- Hotkeys ---

    def _handle_global_hotkey(self, event):
        self._check_hotkey(event)

    def _handle_local_hotkey(self, event):
        self._check_hotkey(event)
        return event

    def _check_hotkey(self, event):
        """Check if the event matches a hotkey (Cmd+Shift+G to toggle, Escape to hide)."""
        flags = event.modifierFlags()
        keycode = event.keyCode()

        # Cmd+Shift+G (keycode 5) — toggle overlay
        cmd_shift = AppKit.NSEventModifierFlagCommand | AppKit.NSEventModifierFlagShift
        if (flags & cmd_shift) == cmd_shift and keycode == 5:
            if self.overlay:
                self.overlay.toggle()

        # Escape (keycode 53) — hide overlay
        if keycode == 53:
            if self.overlay and self.overlay.visible:
                self.overlay.hide()

    # --- Menu Actions ---

    @objc.IBAction
    def showAbout_(self, sender):
        """Show about dialog."""
        alert = NSAlert.alloc().init()
        alert.setMessageText_("GazeTracker")
        alert.setInformativeText_(
            "Version 1.0\n\n"
            "Eye tracking application using MediaPipe Face Mesh.\n"
            "Tracks your gaze and displays a crosshair overlay."
        )
        alert.addButtonWithTitle_("OK")
        alert.runModal()

    @objc.IBAction
    def showSettings_(self, sender):
        """Show or create the settings window."""
        if self.settings_window is None:
            self.settings_window = SettingsWindowController(
                self.settings,
                on_settings_changed=self._on_settings_changed,
            )
        self.settings_window.show()

    @objc.IBAction
    def startCalibration_(self, sender):
        """Re-run calibration."""
        self._start_calibration()

    @objc.IBAction
    def toggleOverlay_(self, sender):
        """Toggle the crosshair overlay."""
        if self.overlay:
            self.overlay.toggle()

    @objc.IBAction
    def toggleWebcamPreview_(self, sender):
        """Toggle the webcam preview window."""
        if self.webcam_preview and self.webcam_preview.is_visible():
            self.webcam_preview.hide()
            self.settings.show_webcam_preview = False
        else:
            self._show_webcam_preview()
            self.settings.show_webcam_preview = True
        self.settings.save()

    # --- Settings ---

    def _on_settings_changed(self, new_settings):
        """Called when settings are changed in the settings window."""
        old = self.settings
        self.settings = new_settings

        # Detect camera config changes that require a device switch
        camera_changed = (
            old.camera_device_index != new_settings.camera_device_index
            or old.camera_resolution_w != new_settings.camera_resolution_w
            or old.camera_resolution_h != new_settings.camera_resolution_h
            or old.camera_fps != new_settings.camera_fps
        )

        if self.overlay:
            self.overlay.update_settings(new_settings)
        if self.confidence_panel:
            self.confidence_panel.update_settings(new_settings)

        # Toggle webcam preview based on setting
        if new_settings.show_webcam_preview:
            self._show_webcam_preview()
        elif self.webcam_preview:
            self.webcam_preview.hide()

        if camera_changed:
            self._switch_camera()

    def _on_panel_position_changed(self, x, y):
        """Save confidence panel position."""
        self.settings.confidence_panel_x = x
        self.settings.confidence_panel_y = y
        self.settings.save()

    def _on_preview_position_changed(self, x, y):
        """Save webcam preview position."""
        self.settings.webcam_preview_x = x
        self.settings.webcam_preview_y = y
        self.settings.save()

    def _show_webcam_preview(self):
        """Show the webcam preview window."""
        if self.webcam_preview is None:
            self.webcam_preview = WebcamPreviewController(
                self.settings,
                on_position_changed=self._on_preview_position_changed,
            )
        self.webcam_preview.show()


def main():
    app = NSApplication.sharedApplication()
    app.setActivationPolicy_(AppKit.NSApplicationActivationPolicyRegular)

    delegate = AppDelegate.alloc().init()
    app.setDelegate_(delegate)

    # Activate the app (bring to front)
    app.activateIgnoringOtherApps_(True)

    app.run()


if __name__ == "__main__":
    main()
