# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for the packaging spike: ONE-FILE, console-mode executable
# named `closet-spike` (`closet-spike.exe` on Windows).
#
#   pyinstaller --noconfirm --clean closet_spike.spec
#
# Add `--distpath <dir> --workpath <dir>` to keep build output out of the repo.

import os
from importlib.metadata import files as dist_files

from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs

HERE = SPECPATH  # folder containing this spec file
NATIVE_SUFFIXES = (".dll", ".dylib", ".so")


def dist_native_libs(dist_name):
    """Native libraries a wheel installs, wherever the wheel puts them.

    Covers the three vendoring layouts in use: auditwheel `<pkg>.libs/` on
    Linux, delocate `<pkg>/.dylibs/` on macOS, and loose DLLs dropped next to
    the extension module on Windows (pillow-heif does this, so
    collect_dynamic_libs("pillow_heif") finds nothing there). Extension
    modules themselves are skipped: PyInstaller collects those as imports.
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


# --- data files -----------------------------------------------------------
datas = [
    (os.path.join(HERE, "static"), "static"),
    (os.path.join(HERE, "fixtures", "tiny_add.onnx"), "fixtures"),
    (os.path.join(HERE, "fixtures", "tiny.heic"), "fixtures"),
]

# The ffmpeg executable ships inside the imageio-ffmpeg wheel as package data
# (imageio_ffmpeg/binaries/ffmpeg-<platform>-v<ver>[.exe]). The contrib hook
# collects it too; listing it here makes the build fail loudly if it is gone.
ffmpeg_datas = collect_data_files("imageio_ffmpeg", subdir="binaries")
if not any(os.path.basename(src).startswith("ffmpeg") for src, _ in ffmpeg_datas):
    raise SystemExit("closet_spike.spec: no ffmpeg binary found in imageio_ffmpeg/binaries")
datas += ffmpeg_datas

# --- native libraries -----------------------------------------------------
onnxruntime_libs = collect_dynamic_libs("onnxruntime")
if not onnxruntime_libs:
    raise SystemExit("closet_spike.spec: no onnxruntime native libraries found")

heif_libs = dist_native_libs("pillow_heif")
if not heif_libs:
    raise SystemExit("closet_spike.spec: no libheif/libde265/x265 libraries found for pillow_heif")

binaries = onnxruntime_libs + heif_libs

print("closet_spike.spec: collected native files:")
for src, dest in ffmpeg_datas + binaries:
    print(f"  {os.path.getsize(src):>12,}  {dest}/{os.path.basename(src)}")

# --- imports PyInstaller cannot see ---------------------------------------
hiddenimports = [
    "_pillow_heif",  # top-level C extension behind pillow_heif
    "imageio_ffmpeg.binaries",  # package looked up via importlib.resources
]

a = Analysis(
    [os.path.join(HERE, "app.py")],
    pathex=[HERE],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # Not needed at run time; keep them out even if present in the build env.
    excludes=[
        "tkinter",
        "onnx",
        "onnxruntime.quantization",
        "onnxruntime.tools",
        "onnxruntime.transformers",
    ],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="closet-spike",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,  # UPX breaks some native DLLs and raises antivirus false positives
    runtime_tmpdir=None,
    console=True,  # spike only; the real app will be windowed
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
