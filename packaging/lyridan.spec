# PyInstaller spec for Lyridan (Windows + macOS).
# Build from the repository root:  pyinstaller --noconfirm packaging/lyridan.spec
import os
import sys

from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs

ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))
sys.path.insert(0, ROOT)
from lyridan import VERSION  # noqa: E402

datas = [
    (os.path.join(ROOT, "lyridan", "data"), os.path.join("lyridan", "data")),
    (os.path.join(ROOT, "assets", "lyridanlogo.ico"), "assets"),
]
datas += collect_data_files("unidic_lite")
datas += collect_data_files("certifi")
binaries = collect_dynamic_libs("fugashi")
binaries += collect_dynamic_libs("onnxruntime")

excludes = [
    "tkinter", "pydoc", "PIL", "torch", "torchaudio", "scipy", "matplotlib",
    "PySide6.QtNetwork", "PySide6.QtQml", "PySide6.QtQuick", "PySide6.QtWebEngineCore",
    "PySide6.QtWebEngineWidgets", "PySide6.Qt3DCore", "PySide6.QtMultimedia", "PySide6.QtPdf",
    "PySide6.QtCharts", "PySide6.QtDataVisualization", "PySide6.QtOpenGL", "PySide6.QtSql",
    "PySide6.QtTest", "PySide6.QtXml", "PySide6.QtSvg", "PySide6.QtDBus", "PySide6.QtDesigner",
]

a = Analysis(
    [os.path.join(ROOT, "Lyridan.py")],
    pathex=[ROOT],
    binaries=binaries,
    datas=datas,
    hiddenimports=["fugashi", "unidic_lite", "lyridan._build", "onnxruntime", "soundfile", "soxr", "shlex", "csv", "collections", "site"],
    excludes=excludes,
    noarchive=False,
)
pyz = PYZ(a.pure)

VERSION_FILE = os.path.join(ROOT, "packaging", "windows", "version_info.txt")  # tools/write_build_info.py
icon = os.path.join(ROOT, "assets", "lyridanlogo.icns" if sys.platform == "darwin" else "lyridanlogo.ico")
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Lyridan",
    console=False,
    icon=icon,
    target_arch=os.environ.get("LYRIDAN_TARGET_ARCH") or None,
    version=VERSION_FILE if sys.platform == "win32" and os.path.exists(VERSION_FILE) else None,
)
coll = COLLECT(exe, a.binaries, a.datas, name="Lyridan", strip=False, upx=False)

if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name="Lyridan.app",
        icon=icon,
        bundle_identifier="com.elevatorisbest.lyridan",
        version=VERSION,
        info_plist={
            "CFBundleName": "Lyridan",
            "CFBundleDisplayName": "Lyridan",
            "CFBundleShortVersionString": VERSION,
            "CFBundleVersion": VERSION,
            "NSHighResolutionCapable": True,
            "LSMinimumSystemVersion": "11.0",
            "NSHumanReadableCopyright": "Elevatorisbest - GPL-2.0",
            "CFBundleDocumentTypes": [
                {"CFBundleTypeName": "Lyridan project", "CFBundleTypeExtensions": ["lyridan"],
                 "CFBundleTypeRole": "Editor"},
                {"CFBundleTypeName": "Lyrics", "CFBundleTypeExtensions": ["ttml", "lrc"],
                 "CFBundleTypeRole": "Viewer"},
            ],
        },
    )
