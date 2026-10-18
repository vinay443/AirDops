# PyInstaller spec for AirDops.exe (one file, no console window).
# Build: pyinstaller --noconfirm --clean airdops.spec
from PyInstaller.utils.hooks import collect_submodules

hidden = (
    collect_submodules("bleak")
    + collect_submodules("winrt")
    + collect_submodules("pycaw")
    + collect_submodules("airdops")
    + ["pystray._win32"]
)

a = Analysis(
    ["scripts/airdops_entry.py"],
    pathex=["src"],
    binaries=[("src/airdops/_vendor/rnnoise.dll", "airdops/_vendor")],
    datas=[("src/airdops/_vendor/pyrnnoise-LICENSE.txt", "airdops/_vendor"), ("THIRD_PARTY_NOTICES.md", ".")],
    hiddenimports=hidden,
    excludes=["tkinter", "matplotlib", "pytest", "IPython"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="AirDops",
    console=False,
    icon="build/AirDops.ico",
    upx=False,
    version=None,
)
