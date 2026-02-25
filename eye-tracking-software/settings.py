"""Settings model and persistence using macOS plist format."""

import os
import plistlib
from dataclasses import dataclass, field, asdict

PLIST_PATH = os.path.expanduser("~/Library/Preferences/com.gazetracker.plist")


@dataclass
class Settings:
    crosshair_color_r: float = 1.0
    crosshair_color_g: float = 1.0
    crosshair_color_b: float = 1.0
    crosshair_color_a: float = 1.0
    crosshair_size: int = 40
    crosshair_line_width: float = 1.5
    crosshair_gap: int = 6
    smoothing_alpha: float = 0.35
    hotkey_modifiers: int = 0  # stored as NSEvent modifier flags
    hotkey_keycode: int = 5  # 'g' key
    hotkey_display: str = "Cmd+Shift+G"
    show_webcam_preview: bool = False
    show_fps: bool = True
    confidence_panel_x: float = 50.0
    confidence_panel_y: float = 50.0
    webcam_preview_x: float = 100.0
    webcam_preview_y: float = 100.0

    def save(self):
        data = asdict(self)
        try:
            with open(PLIST_PATH, "wb") as f:
                plistlib.dump(data, f)
        except Exception as e:
            print(f"Failed to save settings: {e}")

    @classmethod
    def load(cls) -> "Settings":
        if not os.path.exists(PLIST_PATH):
            return cls()
        try:
            with open(PLIST_PATH, "rb") as f:
                data = plistlib.load(f)
            known_fields = {f.name for f in cls.__dataclass_fields__.values()}
            filtered = {k: v for k, v in data.items() if k in known_fields}
            return cls(**filtered)
        except Exception as e:
            print(f"Failed to load settings, using defaults: {e}")
            return cls()
