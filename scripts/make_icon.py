"""Write build/AirDops.ico for the .exe (generated, so no binary in git)."""

import io
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from PIL import Image  # noqa: E402
from PySide6.QtCore import QBuffer, QIODevice  # noqa: E402
from PySide6.QtGui import QGuiApplication  # noqa: E402

from airdops.ui.art import app_icon_image  # noqa: E402

app = QGuiApplication.instance() or QGuiApplication(sys.argv)
buf = QBuffer()
buf.open(QIODevice.OpenModeFlag.WriteOnly)
app_icon_image(256).save(buf, "PNG")
img = Image.open(io.BytesIO(bytes(buf.data())))
out = Path(__file__).resolve().parent.parent / "build" / "AirDops.ico"
out.parent.mkdir(parents=True, exist_ok=True)
img.save(out, format="ICO", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
print(out)
