# PyInstaller spec for the AlomForce desktop app.
#
# Produces a self-contained, relocatable build:
#   - macOS:   dist/AlomForce.app  (drag anywhere, double-click)
#   - Windows: dist/AlomForce/AlomForce.exe  (keep the folder together; the
#              folder can live anywhere — no install path is hardcoded)
#
# Build:  .venv/bin/pyinstaller alomforce.spec --noconfirm
#
# QtWebEngine (the delivery/client map) needs its Chromium runtime bundled, so
# we collect the whole PySide6 package rather than rely on module detection.
import sys
from PyInstaller.utils.hooks import collect_all

datas, binaries, hiddenimports = [], [], []
_d, _b, _h = collect_all('PySide6')
datas += _d
binaries += _b
hiddenimports += _h

# App resources (window icon, etc.), kept at the same relative path the code
# uses via resource_path('app/assets/...').
datas += [('app/assets', 'app/assets')]

icon_file = 'app/assets/alomforce.icns' if sys.platform == 'darwin' \
    else 'app/assets/alomforce.ico'

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=['tkinter'],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='AlomForce',
    debug=False,
    strip=False,
    upx=False,
    console=False,             # windowed GUI app, no terminal
    icon=icon_file,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name='AlomForce',
)

app = BUNDLE(
    coll,
    name='AlomForce.app',
    icon=icon_file,
    bundle_identifier='com.alomforce.desktop',
    info_plist={
        'CFBundleName': 'AlomForce',
        'CFBundleDisplayName': 'AlomForce',
        'NSHighResolutionCapable': True,
    },
)
