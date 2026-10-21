"""Build the RNNoise library from Xiph.org source (build-time only).

Replaces the 14 MB prebuilt DLL from the pyrnnoise wheel. That build ships the
model's full-precision "debug" weights; Xiph's own default build leaves them
out and runs the 8-bit weights, which is what we do here
(``-DDISABLE_DEBUG_FLOAT``, the same define Xiph's configure script sets).

Everything is pinned and verified:
  * source: a fixed git commit of https://github.com/xiph/rnnoise (git checks
    the content against the commit hash),
  * model: the tarball named by that commit's ``model_version`` file, checked
    against the SHA-256 below before it is unpacked.

AirDops' own per-frame helper (``native/airdops_dsp.c``) is compiled into the
same library.

Usage:
  python scripts/build_rnnoise.py                    # clone, download, build
  python scripts/build_rnnoise.py --source DIR       # use an existing checkout
  python scripts/build_rnnoise.py --model-dir DIR    # use rnnoise_data.c/.h from DIR
  python scripts/build_rnnoise.py --out PATH         # write the library somewhere else
"""

from __future__ import annotations

import argparse
import hashlib
import io
import os
import shutil
import subprocess
import sys
import tarfile
import urllib.request
from pathlib import Path

COMMIT = "70f1d256acd4b34a572f999a05c87bf00b67730d"
REPO = "https://github.com/xiph/rnnoise"
MODEL_SHA256 = "0a8755f8e2d834eff6a54714ecc7d75f9932e845df35f8b59bc52a7cfe6e8b37"
MODEL_URL = f"https://media.xiph.org/rnnoise/models/rnnoise_data-{MODEL_SHA256}.tar.gz"
MODEL_FILES = ("rnnoise_data.c", "rnnoise_data.h")

SOURCES = [
    "src/denoise.c",
    "src/rnn.c",
    "src/pitch.c",
    "src/kiss_fft.c",
    "src/celt_lpc.c",
    "src/nnet.c",
    "src/nnet_default.c",
    "src/parse_lpcnet_weights.c",
    "src/rnnoise_data.c",
    "src/rnnoise_tables.c",
]
DEFINES = ["NDEBUG", "DISABLE_DEBUG_FLOAT", "RNNOISE_BUILD", "DLL_EXPORT", "_USE_MATH_DEFINES"]
# rnnoise.h only exports on Windows when WIN32 (no underscore) is defined, which
# clang doesn't do, so set the export attribute directly.
WIN_DEFINES = ["RNNOISE_EXPORT=__declspec(dllexport)"]
REQUIRED_SYMBOLS = (
    "rnnoise_create", "rnnoise_destroy", "rnnoise_process_frame", "rnnoise_get_frame_size",
    "airdops_denoise", "airdops_finish",
)

ROOT = Path(__file__).resolve().parent.parent
VENDOR = ROOT / "src" / "airdops" / "_vendor"
LIB_NAME = "rnnoise.dll" if sys.platform == "win32" else ("librnnoise.dylib" if sys.platform == "darwin" else "librnnoise.so")


def run(cmd: list[str], cwd: Path | None = None) -> None:
    print("+", " ".join(cmd), flush=True)
    subprocess.run(cmd, cwd=cwd, check=True)


def checkout(dest: Path) -> Path:
    if (dest / ".git").is_dir():
        head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=dest, capture_output=True, text=True).stdout.strip()
        if head == COMMIT:
            return dest
        shutil.rmtree(dest)
    dest.mkdir(parents=True, exist_ok=True)
    run(["git", "init", "-q"], dest)
    run(["git", "fetch", "-q", "--depth", "1", REPO, COMMIT], dest)
    run(["git", "-c", "advice.detachedHead=false", "checkout", "-q", "FETCH_HEAD"], dest)
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=dest, capture_output=True, text=True, check=True).stdout.strip()
    if head != COMMIT:
        raise SystemExit(f"unexpected RNNoise commit {head}")
    return dest


def fetch_model(src: Path) -> None:
    if (src / "model_version").read_text().strip() != MODEL_SHA256:
        raise SystemExit("model_version does not match the pinned model hash")
    if all((src / "src" / f).is_file() for f in MODEL_FILES):
        return
    print(f"downloading model {MODEL_URL}", flush=True)
    with urllib.request.urlopen(MODEL_URL, timeout=120) as resp:  # noqa: S310 - fixed https URL, hash-checked
        blob = resp.read()
    digest = hashlib.sha256(blob).hexdigest()
    if digest != MODEL_SHA256:
        raise SystemExit(f"RNNoise model SHA-256 mismatch: {digest}")
    with tarfile.open(fileobj=io.BytesIO(blob), mode="r:gz") as tf:
        for member in tf.getmembers():
            name = Path(member.name).name
            if member.isfile() and name in MODEL_FILES:
                data = tf.extractfile(member)
                assert data is not None
                (src / "src" / name).write_bytes(data.read())
    missing = [f for f in MODEL_FILES if not (src / "src" / f).is_file()]
    if missing:
        raise SystemExit(f"model tarball is missing {missing}")


def _windows_clang() -> str | None:
    found = shutil.which("clang")
    if found:
        return found
    for base in (os.environ.get("ProgramFiles", r"C:\Program Files"), os.environ.get("ProgramFiles(x86)", "")):
        cand = Path(base) / "LLVM" / "bin" / "clang.exe"
        if base and cand.is_file():
            return str(cand)
    return None


def _vcvars() -> Path | None:
    vswhere = Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")) / "Microsoft Visual Studio" / "Installer" / "vswhere.exe"
    if not vswhere.is_file():
        return None
    out = subprocess.run(
        [str(vswhere), "-latest", "-products", "*", "-requires", "Microsoft.VisualStudio.Component.VC.Tools.x86.x64", "-property", "installationPath"],
        capture_output=True, text=True,
    ).stdout.strip()
    bat = Path(out) / "VC" / "Auxiliary" / "Build" / "vcvars64.bat" if out else None
    return bat if bat and bat.is_file() else None


def compile_library(src: Path, out: Path) -> None:
    files = [str(src / s) for s in SOURCES] + [str(ROOT / "native" / "airdops_dsp.c")]
    incs = [str(src / "include"), str(src / "src")]
    out.parent.mkdir(parents=True, exist_ok=True)
    if sys.platform == "win32":
        clang = _windows_clang()
        if clang:
            # Static CRT (/MT equivalent) so the DLL has no runtime dependencies of its own.
            cmd = [clang, "-O2", "-shared", "-fms-runtime-lib=static", "-Wno-deprecated-declarations", "-o", str(out)]
            cmd += [f"-D{d}" for d in DEFINES + WIN_DEFINES] + [f"-I{i}" for i in incs] + files
            run(cmd)
        else:
            bat = _vcvars()
            if bat is None:
                raise SystemExit("no C compiler found (install LLVM clang or Visual Studio Build Tools)")
            cl = ["cl", "/nologo", "/O2", "/MT", "/LD", "/std:c11", f"/Fe{out}", f"/Fo{out.parent}\\"]
            cl += [f"/D{d}" for d in DEFINES + WIN_DEFINES] + [f"/I{i}" for i in incs] + files
            run(["cmd", "/c", f'call "{bat}" >nul && ' + subprocess.list2cmdline(cl)])
        for leftover in (out.with_suffix(".lib"), out.with_suffix(".exp")):
            leftover.unlink(missing_ok=True)
    else:
        cc = os.environ.get("CC", "cc")
        cmd = [cc, "-O2", "-fPIC", "-shared", "-fvisibility=hidden", "-s", "-o", str(out)]
        cmd += [f"-D{d}" for d in DEFINES] + [f"-I{i}" for i in incs] + files + ["-lm"]
        run(cmd)


def check_exports(path: Path) -> None:
    import ctypes

    lib = ctypes.CDLL(str(path.resolve()))
    missing = [name for name in REQUIRED_SYMBOLS if not hasattr(lib, name)]
    if missing:
        raise SystemExit(f"{path.name} does not export {missing}")
    if lib.rnnoise_get_frame_size() != 480:
        raise SystemExit("unexpected RNNoise frame size")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--source", type=Path, help="existing RNNoise checkout at the pinned commit")
    ap.add_argument("--model-dir", type=Path, help="directory containing rnnoise_data.c/.h (skips the download)")
    ap.add_argument("--out", type=Path, default=VENDOR / LIB_NAME)
    args = ap.parse_args()

    src = args.source.resolve() if args.source else checkout(ROOT / "build" / "rnnoise-src")
    if args.model_dir:
        for f in MODEL_FILES:
            shutil.copyfile(args.model_dir / f, src / "src" / f)
    else:
        fetch_model(src)
    compile_library(src, args.out)
    check_exports(args.out)
    VENDOR.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(src / "COPYING", VENDOR / "rnnoise-COPYING.txt")
    data = args.out.read_bytes()
    print(f"RNNoise ready: {args.out} ({len(data) / 1024:.0f} KiB, sha256 {hashlib.sha256(data).hexdigest()})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
