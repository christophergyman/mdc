# GazeTracker

A macOS application that uses your MacBook's built-in webcam to track your gaze and display a real-time crosshair overlay showing where you're looking on screen.

## Features

- **Real-time gaze tracking** using MediaPipe Face Mesh with iris detection
- **20-point calibration** with animated targets and accuracy evaluation
- **Click-through crosshair overlay** that follows your gaze
- **Confidence panel** showing tracking quality, status, and FPS
- **Webcam preview** with landmark visualization for debugging
- **Settings panel** for customizing crosshair appearance, smoothing, and hotkeys
- **Proper macOS app** with dock icon, menu bar, and native UI

## Requirements

- macOS 12.0+ (Monterey or later)
- Apple Silicon Mac (M1/M2/M3/M4) — also works on Intel but optimized for ARM
- Python 3.10+
- Built-in FaceTime camera or compatible USB webcam

## Quick Start

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Run directly

```bash
python main.py
```

### 3. Build as .app bundle (optional)

```bash
python setup.py py2app
```

The built app will be in `dist/GazeTracker.app`. You can copy it to `/Applications`.

## Usage

1. **Launch** — the app opens and requests camera access (first time only)
2. **Calibration** — follow the blue dots across the screen, keeping your head still
3. **Tracking** — a crosshair appears where you're looking
4. **Settings** — access via the menu bar or `Cmd+,`
5. **Toggle overlay** — press `Cmd+Shift+G` to show/hide the crosshair

## Keyboard Shortcuts

| Shortcut | Action |
|---|---|
| `Cmd+Shift+G` | Toggle crosshair overlay |
| `Cmd+R` | Recalibrate |
| `Cmd+W` | Toggle webcam preview |
| `Cmd+,` | Open settings |
| `Cmd+Q` | Quit |

## Settings

| Setting | Description | Default |
|---|---|---|
| Crosshair colour | Color of the crosshair lines | White |
| Crosshair size | Arm length in pixels | 40px |
| Smoothing | EMA alpha (lower = smoother, higher = reactive) | 0.35 |
| Show webcam preview | Live camera feed with landmarks | Off |
| Show FPS | FPS counter in confidence panel | On |

## How It Works

1. **Face detection**: MediaPipe Face Mesh detects 468 facial landmarks + iris positions
2. **Feature extraction**: Normalized iris positions and head pose (yaw/pitch) form a 6D feature vector
3. **Calibration**: Collects feature vectors at 20 known screen positions, trains a Ridge Regression model with polynomial features
4. **Prediction**: Each frame's features are fed through the model to predict screen coordinates
5. **Smoothing**: Exponential moving average reduces jitter
6. **Display**: PyObjC renders a click-through crosshair at the predicted gaze position

## Troubleshooting

### Camera access denied
Go to **System Settings > Privacy & Security > Camera** and enable access for GazeTracker (or Terminal/Python if running directly).

### MediaPipe installation issues on Apple Silicon
```bash
pip install mediapipe --no-cache-dir
```
If that fails, try:
```bash
pip install mediapipe-silicon
```

### High calibration error
- Ensure good, even lighting on your face
- Sit at a comfortable distance (50–70cm from screen)
- Keep your head as still as possible during calibration
- Make sure your face is fully visible to the camera
- Try closing one eye if you wear glasses with strong reflections

### Low FPS
- Close other camera-using apps
- Ensure no heavy CPU tasks are running
- The app targets 30fps on Apple Silicon — Intel Macs may be slower

### py2app build issues
```bash
# Clean previous builds
rm -rf build dist
# Rebuild
python setup.py py2app
```

If you get import errors in the built app, try adding the missing package to the `packages` list in `setup.py`.

## Architecture

```
main.py               — App lifecycle, menus, tracking loop coordination
calibration.py        — Fullscreen calibration with animated targets
gaze_estimator.py     — MediaPipe feature extraction + regression model
overlay.py            — Transparent click-through crosshair window
confidence_panel.py   — Floating tracking quality HUD
settings.py           — Settings model + plist persistence
settings_window.py    — Native preferences window
webcam_preview.py     — Camera feed with landmark overlays
```

## License

MIT
