"""Test: borderless NSWindow button behavior with performClick_.

Test A: Standard NSWindow (borderless) — canBecomeKeyWindow=NO
Test B: KeyableWindow (borderless) — canBecomeKeyWindow=YES

Uses performClick_ (no Accessibility permissions needed).
Check /tmp/test_btn.log for results.
"""

import objc
import AppKit
from Foundation import NSObject, NSMakeRect, NSTimer
from AppKit import (
    NSApplication, NSWindow, NSView, NSScreen, NSColor, NSFont,
    NSButton, NSTextField, NSBezelStyleRounded,
    NSWindowStyleMaskBorderless, NSBackingStoreBuffered,
)

LOG_PATH = "/tmp/test_btn.log"

def log(msg):
    with open(LOG_PATH, "a") as f:
        f.write(msg + "\n")


class KeyableWindow(NSWindow):
    def canBecomeKeyWindow(self):
        return True


class ButtonTester:
    """Plain Python class target (like CalibrationController)."""

    def __init__(self, label, window_class, y_offset):
        self.label = label
        self.fired = False

        self.window = window_class.alloc().initWithContentRect_styleMask_backing_defer_(
            NSMakeRect(50, y_offset, 400, 120),
            NSWindowStyleMaskBorderless,
            NSBackingStoreBuffered,
            False,
        )
        self.window.setLevel_(AppKit.NSStatusWindowLevel)
        self.window.setBackgroundColor_(NSColor.darkGrayColor())

        view = NSView.alloc().initWithFrame_(NSMakeRect(0, 0, 400, 120))
        self.window.setContentView_(view)

        title = NSTextField.alloc().initWithFrame_(NSMakeRect(10, 90, 380, 20))
        title.setStringValue_(label)
        title.setEditable_(False)
        title.setBezeled_(False)
        title.setDrawsBackground_(False)
        title.setTextColor_(NSColor.whiteColor())
        title.setFont_(NSFont.boldSystemFontOfSize_(13))
        view.addSubview_(title)

        self.status = NSTextField.alloc().initWithFrame_(NSMakeRect(150, 15, 230, 20))
        self.status.setStringValue_("waiting...")
        self.status.setEditable_(False)
        self.status.setBezeled_(False)
        self.status.setDrawsBackground_(False)
        self.status.setTextColor_(NSColor.yellowColor())
        self.status.setFont_(NSFont.monospacedSystemFontOfSize_weight_(12, 0.0))
        view.addSubview_(self.status)

        self.button = NSButton.alloc().initWithFrame_(((20, 10), (120, 32)))
        self.button.setTitle_("Click Me")
        self.button.setBezelStyle_(NSBezelStyleRounded)
        self.button.setTarget_(self)
        self.button.setAction_(objc.selector(self._on_click, signature=b"v@:@"))
        view.addSubview_(self.button)

        self.window.makeKeyAndOrderFront_(None)

    def _on_click(self, sender):
        self.fired = True
        log(f"[{self.label}] ACTION FIRED!")
        self.status.setStringValue_("ACTION FIRED!")


class AppDel(NSObject):
    def init(self):
        self = objc.super(AppDel, self).init()
        return self

    def applicationDidFinishLaunching_(self, notification):
        with open(LOG_PATH, "w") as f:
            f.write("=== performClick_ test ===\n")

        self.a = ButtonTester("A: Standard NSWindow (borderless)", NSWindow, 300)
        self.b = ButtonTester("B: KeyableWindow (borderless)", KeyableWindow, 150)

        log(f"A canBecomeKey={self.a.window.canBecomeKeyWindow()}")
        log(f"B canBecomeKey={self.b.window.canBecomeKeyWindow()}")

        # Programmatic click after 1s
        NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
            1.0, self, "doTest:", None, False
        )
        NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
            3.0, self, "doQuit:", None, False
        )

    @objc.typedSelector(b"v@:@")
    def doTest_(self, timer):
        log("\n--- performClick_ on both buttons ---")
        self.a.button.performClick_(None)
        self.b.button.performClick_(None)
        log(f"\nA fired={self.a.fired}")
        log(f"B fired={self.b.fired}")
        if self.a.fired and self.b.fired:
            log("RESULT: Both work with performClick_ (programmatic)")
            log("Issue must be with real mouse events + canBecomeKeyWindow")
        elif self.b.fired and not self.a.fired:
            log("RESULT: Only KeyableWindow works")
        else:
            log(f"RESULT: unexpected — A={self.a.fired}, B={self.b.fired}")

    @objc.typedSelector(b"v@:@")
    def doQuit_(self, timer):
        NSApplication.sharedApplication().terminate_(None)


def main():
    app = NSApplication.sharedApplication()
    app.setActivationPolicy_(AppKit.NSApplicationActivationPolicyRegular)
    d = AppDel.alloc().init()
    app.setDelegate_(d)
    app.activateIgnoringOtherApps_(True)
    app.run()


if __name__ == "__main__":
    main()
