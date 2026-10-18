"""Write build/AirDops.ico for the .exe (generated, so no binary in git)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from airdops.icons import save_ico  # noqa: E402

out = Path(__file__).resolve().parent.parent / "build" / "AirDops.ico"
out.parent.mkdir(parents=True, exist_ok=True)
save_ico(str(out))
print(out)
