# PyInstaller spec for AirDops (no console window).
#   set AIRDOPS_ONEDIR=1 & pyinstaller --noconfirm airdops.spec -> dist/AirDops/ (folder: used by the installer
#                                                                  and the portable zip; starts fastest)
#   pyinstaller --noconfirm --clean airdops.spec                -> dist/AirDops.exe (single file, local use)
#
# Size matters (people download this over slow links), so the bundle is trimmed to what a
# Windows x64 build actually loads. CI prints the biggest files and enforces a size budget
# (scripts/size_report.py); check it after adding a dependency.
import os

from PyInstaller.utils.hooks import collect_submodules

ONEDIR = bool(os.environ.get("AIRDOPS_ONEDIR"))

hidden = (
    # Only bleak's WinRT backend; the Linux/macOS/Android backends are never used.
    collect_submodules(
        "bleak", filter=lambda n: not any(x in n for x in (".bluezdbus", ".corebluetooth", ".p4android"))
    )
    + collect_submodules("winrt")
    # Just the COM interface definitions we use (pycaw.utils/callbacks would pull in psutil).
    + ["pycaw.api.mmdeviceapi", "pycaw.api.mmdeviceapi.depend", "pycaw.api.policyconfig", "pycaw.constants"]
    + collect_submodules("airdops")
)

a = Analysis(
    ["scripts/airdops_entry.py"],
    pathex=["src"],
    binaries=[("src/airdops/_vendor/rnnoise.dll", "airdops/_vendor")],
    datas=[
        ("src/airdops/_vendor/rnnoise-COPYING.txt", "airdops/_vendor"),
        ("src/airdops/ui/fonts/*.ttf", "airdops/ui/fonts"),
        ("src/airdops/ui/fonts/Inter-OFL.txt", "airdops/ui/fonts"),
        ("THIRD_PARTY_NOTICES.md", "."),
    ],
    hiddenimports=hidden,
    excludes=[
        "tkinter", "matplotlib", "pytest", "IPython", "PIL", "numpy", "psutil",
        "pycaw.utils", "pycaw.callbacks", "pycaw.pycaw", "pycaw.magic",
        # No TLS or networking anywhere in the app (see SECURITY.md); this also drops OpenSSL.
        "ssl", "_ssl", "_hashlib", "ftplib", "smtplib", "imaplib", "poplib", "xmlrpc", "http.server",
        # Developer tooling from the standard library.
        "pydoc", "pydoc_data", "doctest", "unittest", "pdb", "lib2to3",
        # Mail/web/XML/archive modules nothing in the app or its dependencies uses at runtime
        # (unicodedata is only reached through the IDNA codec for hostnames).
        "email", "http", "urllib.request", "mimetypes", "xml", "pyexpat", "_elementtree",
        "unicodedata", "stringprep", "encodings.idna", "multiprocessing", "concurrent.futures.process",
        "tarfile", "lzma", "_lzma", "bz2", "_bz2",
        "PySide6.QtNetwork", "PySide6.QtQml", "PySide6.QtQuick", "PySide6.QtPdf", "PySide6.QtSvg",
        "PySide6.QtOpenGL", "PySide6.QtSql", "PySide6.QtTest", "PySide6.QtConcurrent", "PySide6.QtDBus",
    ],
    noarchive=False,
)

# Files a Windows x64 AirDops never loads. Matched against the bundled path.
_DROP = (
    "opengl32sw.dll",              # software OpenGL fallback; we draw with QPainter
    "Qt6Network.dll", "Qt6Svg.dll", "Qt6OpenGL.dll", "Qt6Pdf.dll", "Qt6Qml", "Qt6Quick",
    "PySide6/translations/",       # Qt's own UI strings; AirDops is English-only
    "PySide6/plugins/imageformats/",
    "PySide6/plugins/iconengines/",
    "PySide6/plugins/generic/",
    "PySide6/plugins/networkinformation/",
    "PySide6/plugins/tls/",
    "PySide6/plugins/platforms/qdirect2d.dll",
    "PySide6/plugins/platforms/qminimal.dll",
    "PySide6/plugins/platforms/qoffscreen.dll",
    "libcrypto-", "libssl-",       # OpenSSL (Python's ssl module and Qt's TLS plugin)
    # The Universal C Runtime is part of Windows 10 and 11 (AirDops needs Windows 10+ for WinRT).
    "api-ms-win-", "ucrtbase.dll",
    # PortAudio builds for other CPUs/OSes; sounddevice loads libportaudio64bit.dll on x64.
    "portaudio-binaries/libportaudio32bit", "portaudio-binaries/libportaudioarm64",
    "portaudio-binaries/libportaudio64bit-asio", "portaudio-binaries/libportaudio.dylib",
    "portaudio-binaries/README",
)


def _keep(entry):
    dest = entry[0].replace("\\", "/")
    return not any(pat in dest for pat in _DROP)


a.binaries = [b for b in a.binaries if _keep(b)]
a.datas = [d for d in a.datas if _keep(d)]

pyz = PYZ(a.pure)
common = dict(name="AirDops", console=False, icon="build/AirDops.ico", upx=False, version="build/version_info.txt")
if ONEDIR:
    exe = EXE(pyz, a.scripts, [], exclude_binaries=True, **common)
    coll = COLLECT(exe, a.binaries, a.datas, name="AirDops", upx=False)
else:
    exe = EXE(pyz, a.scripts, a.binaries, a.datas, [], **common)
