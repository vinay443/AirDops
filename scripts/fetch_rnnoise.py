"""Download the RNNoise DLL used for noise suppression (build-time only).

The DLL comes from the ``pyrnnoise`` wheel on PyPI (a build of Xiph.org's
BSD-licensed RNNoise). We pin an exact version *and* the SHA-256 of the wheel,
so a tampered or swapped download fails loudly instead of being bundled.

Usage:  python scripts/fetch_rnnoise.py
"""

from __future__ import annotations

import hashlib
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

VERSION = "0.4.5"
WHEEL = f"pyrnnoise-{VERSION}-py3-none-win_amd64.whl"
SHA256 = "f46015e5a58212d2883bf8e5a2cafb3c6b115176d8039f8340132cb24866b7da"
MEMBER = f"pyrnnoise-{VERSION}.data/purelib/pyrnnoise/rnnoise.dll"
LICENSE_MEMBER = f"pyrnnoise-{VERSION}.dist-info/licenses/LICENSE"

ROOT = Path(__file__).resolve().parent.parent
DEST = ROOT / "src" / "airdops" / "_vendor"


def main() -> int:
    DEST.mkdir(parents=True, exist_ok=True)
    target = DEST / "rnnoise.dll"
    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run(
            [
                sys.executable, "-m", "pip", "download", f"pyrnnoise=={VERSION}",
                "--no-deps", "--only-binary=:all:", "--platform", "win_amd64",
                "--python-version", "3.12", "--dest", tmp, "--quiet",
            ],
            check=True,
        )
        wheel = Path(tmp) / WHEEL
        digest = hashlib.sha256(wheel.read_bytes()).hexdigest()
        if digest != SHA256:
            print(f"SHA-256 mismatch for {WHEEL}: {digest}", file=sys.stderr)
            return 1
        with zipfile.ZipFile(wheel) as zf:
            target.write_bytes(zf.read(MEMBER))
            (DEST / "pyrnnoise-LICENSE.txt").write_bytes(zf.read(LICENSE_MEMBER))
    print(f"RNNoise ready: {target} ({target.stat().st_size // 1024} KiB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
