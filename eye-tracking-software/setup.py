"""py2app setup script for GazeTracker."""

from setuptools import setup

APP = ['main.py']
DATA_FILES = []
OPTIONS = {
    'argv_emulation': False,
    'iconfile': 'AppIcon.icns',
    'plist': 'Info.plist',
    'packages': [
        'cv2', 'mediapipe', 'sklearn', 'numpy',
        'objc', 'AppKit', 'Foundation', 'Quartz',
        'pynput',
    ],
    'includes': [
        'settings', 'gaze_estimator', 'calibration',
        'overlay', 'confidence_panel', 'settings_window',
        'webcam_preview',
    ],
    'excludes': ['tkinter', 'matplotlib', 'scipy.spatial.cKDTree'],
    'site_packages': True,
}

setup(
    app=APP,
    name='GazeTracker',
    data_files=DATA_FILES,
    options={'py2app': OPTIONS},
    setup_requires=['py2app'],
)
