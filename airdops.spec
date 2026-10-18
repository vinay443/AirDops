# PyInstaller spec for AirDops.exe (no console window).
#   pyinstaller --noconfirm --clean airdops.spec                -> dist/AirDops.exe (portable, one file)
#   set AIRDOPS_ONEDIR=1 & pyinstaller --noconfirm airdops.spec -> dist/AirDops/ (folder, used by the installer;
#                                                                  starts faster because nothing is unpacked)
import os

from PyInstaller.utils.hooks import collect_submodules

ONEDIR = bool(os.environ.get("AIRDOPS_ONEDIR"))

hidden = (
    collect_submodules("bleak")
    + collect_submodules("winrt")
    + collect_submodules("pycaw")
    + collect_submodules("airdops")
)

a = Analysis(
    ["scripts/airdops_entry.py"],
    pathex=["src"],
    binaries=[("src/airdops/_vendor/rnnoise.dll", "airdops/_vendor")],
    datas=[
        ("src/airdops/_vendor/pyrnnoise-LICENSE.txt", "airdops/_vendor"),
        ("src/airdops/ui/fonts/*.ttf", "airdops/ui/fonts"),
        ("src/airdops/ui/fonts/Inter-OFL.txt", "airdops/ui/fonts"),
        ("THIRD_PARTY_NOTICES.md", "."),
    ],
    hiddenimports=hidden,
    excludes=[
        "tkinter", "matplotlib", "pytest", "IPython", "PIL",
        "PySide6.QtQml", "PySide6.QtQuick", "PySide6.QtPdf", "PySide6.QtSvg",
        "PySide6.QtOpenGL", "PySide6.QtSql", "PySide6.QtTest", "PySide6.QtConcurrent",
    ],
    noarchive=False,
)
pyz = PYZ(a.pure)
common = dict(name="AirDops", console=False, icon="build/AirDops.ico", upx=False, version="build/version_info.txt")
if ONEDIR:
    exe = EXE(pyz, a.scripts, [], exclude_binaries=True, **common)
    coll = COLLECT(exe, a.binaries, a.datas, name="AirDops", upx=False)
else:
    exe = EXE(pyz, a.scripts, a.binaries, a.datas, [], **common)
