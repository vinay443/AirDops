"""Render the UI with sample data to PNGs (docs screenshots and CI check).

    QT_QPA_PLATFORM=offscreen python scripts/render_previews.py [out_dir]
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from PySide6.QtWidgets import QApplication  # noqa: E402

from airdops.ui import theme  # noqa: E402
from airdops.ui.preview import render_all  # noqa: E402

app = QApplication.instance() or QApplication(sys.argv)
theme.load_fonts()
out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("build/previews")
for p in render_all(out):
    print(p)
