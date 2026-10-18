"""Write build/version_info.txt (Windows file properties: name, version, company)."""

import re
import sys
from pathlib import Path

root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root / "src"))
from airdops import __version__  # noqa: E402

nums = [int(x) for x in re.findall(r"\d+", __version__)[:3]] + [0, 0, 0]
v = tuple(nums[:3]) + (0,)
text = f"""VSVersionInfo(
  ffi=FixedFileInfo(filevers={v}, prodvers={v}, mask=0x3f, flags=0x0, OS=0x40004, fileType=0x1, subtype=0x0, date=(0, 0)),
  kids=[
    StringFileInfo([StringTable('040904B0', [
      StringStruct('CompanyName', 'AirDops'),
      StringStruct('FileDescription', 'AirDops - full-quality AirPods audio for gaming'),
      StringStruct('FileVersion', '{__version__}'),
      StringStruct('InternalName', 'AirDops'),
      StringStruct('LegalCopyright', 'MIT License'),
      StringStruct('OriginalFilename', 'AirDops.exe'),
      StringStruct('ProductName', 'AirDops'),
      StringStruct('ProductVersion', '{__version__}')])]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])
  ]
)
"""
out = root / "build" / "version_info.txt"
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(text, encoding="utf-8")
print(out, __version__)
