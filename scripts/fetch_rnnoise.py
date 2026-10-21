"""Download the old prebuilt RNNoise library, as a *test reference only*.

Up to v0.3 AirDops shipped the RNNoise DLL from the ``pyrnnoise`` wheel. It
is now built from Xiph.org source (``scripts/build_rnnoise.py``) and is much
smaller; CI keeps this script to fetch the old library so
``tests/test_rnnoise_quality.py`` can check the new build sounds the same.
The reference is never bundled into the app.

The wheel version and its SHA-256 are pinned, so a swapped file fails loudly.

Usage:  python scripts/fetch_rnnoise.py [--dest build/reference]
Then:   AIRDOPS_RNNOISE_REFERENCE=<printed path> python -m pytest tests/test_rnnoise_quality.py
"""

from __future__ import annotations

import argparse
import hashlib
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

VERSION = "0.4.5"
WHEELS = {
    # platform tag: (wheel file, sha256, member, saved as)
    "win32": (
        f"pyrnnoise-{VERSION}-py3-none-win_amd64.whl",
        "f46015e5a58212d2883bf8e5a2cafb3c6b115176d8039f8340132cb24866b7da",
        f"pyrnnoise-{VERSION}.data/purelib/pyrnnoise/rnnoise.dll",
        "rnnoise_ref.dll",
        "win_amd64",
    ),
    "linux": (
        f"pyrnnoise-{VERSION}-py3-none-manylinux1_x86_64.whl",
        "c095114532f9fa21f621084c879d72c93aaa0c9dbe38b662a63577bada2c214e",
        f"pyrnnoise-{VERSION}.data/purelib/pyrnnoise/librnnoise.so",
        "librnnoise_ref.so",
        "manylinux1_x86_64",
    ),
}

ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dest", type=Path, default=ROOT / "build" / "reference")
    args = ap.parse_args()
    key = "win32" if sys.platform == "win32" else "linux"
    wheel_name, sha256, member, saved_as, platform = WHEELS[key]
    args.dest.mkdir(parents=True, exist_ok=True)
    target = args.dest / saved_as
    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run(
            [
                sys.executable, "-m", "pip", "download", f"pyrnnoise=={VERSION}",
                "--no-deps", "--only-binary=:all:", "--platform", platform,
                "--python-version", "3.12", "--dest", tmp, "--quiet",
            ],
            check=True,
        )
        wheel = Path(tmp) / wheel_name
        digest = hashlib.sha256(wheel.read_bytes()).hexdigest()
        if digest != sha256:
            print(f"SHA-256 mismatch for {wheel_name}: {digest}", file=sys.stderr)
            return 1
        with zipfile.ZipFile(wheel) as zf:
            target.write_bytes(zf.read(member))
    print(target)
    return 0


if __name__ == "__main__":
    sys.exit(main())
