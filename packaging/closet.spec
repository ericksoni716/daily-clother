# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for Closet (the real build; packaging/spike/ was the proof).
#
#   python -m PyInstaller --noconfirm --clean packaging/closet.spec \
#       --distpath <dir> --workpath <dir>
#
# What it produces depends on the OS it runs on:
#   Windows  dist/Closet.exe   one file, windowed (no console), with an icon
#   macOS    dist/Closet.app   windowed menu-bar app (LSUIElement, bundle id
#                              app.closet), one-folder inside the bundle; the
#                              release workflow zips it with `ditto`
#   Linux    dist/closet       one file, console; for local verification only
#
# Before building: the frontend must be built into backend/closet/web/
# (`npm ci && npm run build` in frontend/), and the release workflow writes
# backend/closet/_build_version.py. The build stops if the web page, the
# migrations or the demo data are missing.

import os
import sys
from importlib.metadata import files as dist_files

from PyInstaller.utils.hooks import collect_dynamic_libs

HERE = SPECPATH  # packaging/
REPO = os.path.dirname(HERE)
BACKEND = os.path.join(REPO, "backend")
PKG = os.path.join(BACKEND, "closet")

IS_WIN = sys.platform == "win32"
IS_MAC = sys.platform == "darwin"
NATIVE_SUFFIXES = (".dll", ".dylib", ".so")
SKIP_NAMES = {"__pycache__", ".DS_Store", "Thumbs.db"}


def fail(message):
    raise SystemExit(f"closet.spec: {message}")


def dist_native_libs(dist_name):
    """Native libraries a wheel installs, wherever the wheel puts them.

    Same as in the spike: covers auditwheel `<pkg>.libs/` (Linux), delocate
    `<pkg>/.dylibs/` (macOS) and loose DLLs in site-packages (pillow-heif on
    Windows, where collect_dynamic_libs("pillow_heif") finds nothing).
    Extension modules are skipped; PyInstaller collects those as imports.
    """
    found = []
    for entry in dist_files(dist_name) or []:
        name = entry.name.lower()
        is_lib = name.endswith(NATIVE_SUFFIXES) or ".so." in name
        is_extension = name.endswith(".pyd") or ".cpython-" in name or ".abi3." in name
        if not is_lib or is_extension:
            continue
        src = str(entry.locate())
        if os.path.isfile(src):
            found.append((src, os.path.dirname(str(entry)) or "."))
    return found


def tree(src_dir, dest_dir, suffixes=None):
    """(source file, destination folder) pairs for every file under src_dir."""
    out = []
    for root, dirs, names in os.walk(src_dir):
        dirs[:] = sorted(d for d in dirs if d not in SKIP_NAMES)
        rel = os.path.relpath(root, src_dir)
        dest = dest_dir if rel == "." else os.path.join(dest_dir, rel)
        for name in sorted(names):
            if name in SKIP_NAMES or name.endswith(".pyc"):
                continue
            if suffixes and not name.lower().endswith(suffixes):
                continue
            out.append((os.path.join(root, name), dest))
    return out


def build_version():
    """VERSION from closet/_build_version.py (written by the release workflow)."""
    path = os.path.join(PKG, "_build_version.py")
    if not os.path.isfile(path):
        return None
    namespace = {}
    with open(path, encoding="utf-8") as fh:
        exec(fh.read(), namespace)
    return str(namespace.get("VERSION") or "") or None


# --- bundled data: <_MEIPASS>/closet/{migrations,demo_data,web} -------------
# config.bundle_dir() looks for exactly this layout.
for required in ("web/index.html", "demo_data/items.json", "demo_data/tiny.heic", "demo_data/selfcheck.webp"):
    if not os.path.isfile(os.path.join(PKG, required)):
        hint = " Build the frontend first: `npm ci && npm run build` in frontend/." if required.startswith("web/") else ""
        fail(f"backend/closet/{required} is missing.{hint}")

migrations = tree(os.path.join(PKG, "migrations"), os.path.join("closet", "migrations"), suffixes=(".sql",))
if not migrations:
    fail("no backend/closet/migrations/*.sql files found")

datas = (
    migrations
    + tree(os.path.join(PKG, "demo_data"), os.path.join("closet", "demo_data"))
    + tree(os.path.join(PKG, "web"), os.path.join("closet", "web"))
)

# --- native libraries -----------------------------------------------------
onnxruntime_libs = collect_dynamic_libs("onnxruntime")
if not onnxruntime_libs:
    fail("no onnxruntime native libraries found")

heif_libs = dist_native_libs("pillow_heif")
if not heif_libs:
    fail("no libheif/libde265/x265 libraries found for pillow_heif")

binaries = onnxruntime_libs + heif_libs

print("closet.spec: collected native files:")
for src, dest in binaries:
    print(f"  {os.path.getsize(src):>12,}  {dest}/{os.path.basename(src)}")
print(f"closet.spec: {len(datas)} data files ({sum(os.path.getsize(s) for s, _ in datas):,} bytes) under closet/")

# --- imports PyInstaller cannot see ---------------------------------------
# Every closet module, so a lazily imported one is never missed.
closet_modules = sorted(
    "closet." + name[:-3]
    for name in os.listdir(PKG)
    if name.endswith(".py") and name not in ("__init__.py", "__main__.py")
)

# pystray picks its backend at import time with relative imports inside
# functions. The contrib hook already collects all pystray submodules; the
# platform backend is listed here too so a hook change cannot drop it. The
# program runs without a tray if the backend cannot load (closet/tray.py).
if IS_WIN:
    tray_imports = ["pystray._win32"]
elif IS_MAC:
    tray_imports = ["pystray._darwin", "AppKit", "Foundation", "objc", "PyObjCTools", "PyObjCTools.MachSignals"]
else:
    tray_imports = ["pystray._xorg", "pystray._appindicator", "pystray._gtk"]

hiddenimports = closet_modules + ["_pillow_heif", "pystray", "pystray._dummy"] + tray_imports

excludes = [
    "tkinter",
    "_tkinter",
    "onnx",
    "onnxruntime.quantization",
    "onnxruntime.tools",
    "onnxruntime.transformers",
    "setuptools",
    "pkg_resources",
    "distutils",
    "pip",
    "pytest",
    "_pytest",
    "numpy.f2py",
    "IPython",
    "matplotlib",
    "tests",
]

# --- icon -----------------------------------------------------------------
# Drawn by closet.tray.icon_image() so the tray icon and the program icon
# match. Written into the work folder, never into the repository.
icon_file = None
if IS_WIN or IS_MAC:
    sys.path.insert(0, BACKEND)
    try:
        from closet.tray import icon_image

        os.makedirs(workpath, exist_ok=True)
        if IS_WIN:
            icon_file = os.path.join(workpath, "closet.ico")
            icon_image(256).save(icon_file, format="ICO",
                                 sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
        else:
            icon_file = os.path.join(workpath, "closet.icns")
            icon_image(1024).save(icon_file, format="ICNS")
        print(f"closet.spec: icon written to {icon_file}")
    except Exception as exc:  # an icon is nice to have; never fail the build for it
        print(f"closet.spec: WARNING: no icon ({type(exc).__name__}: {exc})")
        icon_file = None
    finally:
        sys.path.remove(BACKEND)

version = build_version()
print(f"closet.spec: version {version or '(none; _build_version.py not written, runs as 0.1.0-dev)'}")

a = Analysis(
    [os.path.join(PKG, "__main__.py")],
    pathex=[BACKEND],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

if IS_MAC:
    # A one-file .app is deprecated in PyInstaller 6 (and slow to start), so
    # the bundle holds a one-folder build.
    exe = EXE(
        pyz,
        a.scripts,
        [],
        exclude_binaries=True,
        name="Closet",
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=False,
        console=False,
        disable_windowed_traceback=False,
        argv_emulation=False,
        target_arch=None,
        codesign_identity=None,  # PyInstaller's ad-hoc signature only
        entitlements_file=None,
        icon=icon_file,
    )
    coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="Closet")
    app = BUNDLE(
        coll,
        name="Closet.app",
        icon=icon_file,
        bundle_identifier="app.closet",
        version=version or "0.1.0",
        info_plist={
            "CFBundleName": "Closet",
            "CFBundleDisplayName": "Closet",
            "CFBundleShortVersionString": version or "0.1.0",
            "CFBundleVersion": version or "0.1.0",
            "LSUIElement": True,  # menu-bar app: no Dock icon, no app menu
            "LSMinimumSystemVersion": "14.0",  # onnxruntime / numpy arm64 wheels are macosx_14_0
            "NSHighResolutionCapable": True,
        },
    )
else:
    exe = EXE(
        pyz,
        a.scripts,
        a.binaries,
        a.datas,
        [],
        name="Closet" if IS_WIN else "closet",
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=False,  # UPX breaks some native DLLs and raises antivirus false positives
        runtime_tmpdir=None,
        console=not IS_WIN,  # Windows: no console window; Linux build is for local checks
        disable_windowed_traceback=False,
        argv_emulation=False,
        target_arch=None,
        codesign_identity=None,
        entitlements_file=None,
        icon=icon_file,
    )
