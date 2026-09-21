#!/usr/bin/env python3
"""Development build helper for the luxcore C++ extension.

Prefers an in-place CMake build so ``import luxcore`` works from the repo
root without reinstalling. Falls back to ``pip install -e .`` when cmake
configuration fails.

Usage:
    python scripts/build_luxcore.py [--clean] [--threads N] [--no-openmp]
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BUILD_DIR = ROOT / "build" / "luxcore"


def _run(cmd: list[str], **kw) -> None:
    print("+", " ".join(cmd), flush=True)
    subprocess.run(cmd, check=True, **kw)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--clean", action="store_true")
    ap.add_argument("--threads", type=int, default=os.cpu_count() or 4)
    ap.add_argument("--build-type", default="Release")
    args = ap.parse_args()

    if args.clean and BUILD_DIR.exists():
        shutil.rmtree(BUILD_DIR)
    for stale in ROOT.glob("luxcore*.so"):
        stale.unlink()

    BUILD_DIR.mkdir(parents=True, exist_ok=True)
    cmake = shutil.which("cmake") or shutil.which("cmake3")
    if cmake is None:
        # pip's cmake package exposes itself via python -m cmake
        try:
            _run([sys.executable, "-m", "cmake", "--version"])
            cmake = f"{sys.executable} -m cmake"
        except subprocess.CalledProcessError:
            print("cmake not found; install it (pip install cmake)", file=sys.stderr)
            return 1

    env = dict(os.environ)
    # User-space Python headers fallback (no sudo): if the interpreter's
    # INCLUDEPY lacks Python.h (distro venv without python3-dev), point the
    # build at headers extracted from the python3.14-dev .deb into /tmp/pydev.
    try:
        inc = subprocess.run(
            [sys.executable, "-c",
             "import sysconfig; print(sysconfig.get_config_var('INCLUDEPY'))"],
            check=True, capture_output=True, text=True,
        ).stdout.strip()
    except subprocess.CalledProcessError:
        inc = ""
    if not inc or not Path(inc, "Python.h").exists():
        for cand in ("/tmp/pydev/root/usr/include/python3.14",):
            if Path(cand, "Python.h").exists():
                env.setdefault("LUXCORE_PYTHON_INCLUDE", cand)
                print(f"using user-space Python headers: {cand}")
                break

    configure = [
        *(cmake.split() if " " in cmake else [cmake]),
        "-S",
        str(ROOT),
        "-B",
        str(BUILD_DIR),
        f"-DCMAKE_BUILD_TYPE={args.build_type}",
        f"-DPython_EXECUTABLE={sys.executable}",
    ]
    build = [
        *(cmake.split() if " " in cmake else [cmake]),
        "--build",
        str(BUILD_DIR),
        "-j",
        str(args.threads),
    ]
    try:
        _run(configure, env=env)
        _run(build, env=env)
    except subprocess.CalledProcessError:
        return 1

    # Copy the built extension to the repo root for `import luxcore`.
    candidates = list(BUILD_DIR.rglob("luxcore*.so"))
    if not candidates:
        # LIBRARY_OUTPUT_DIRECTORY points at the source root already.
        candidates = list(ROOT.glob("luxcore*.so"))
    if not candidates:
        print("build succeeded but no luxcore*.so found", file=sys.stderr)
        return 1
    for so in candidates:
        dest = ROOT / so.name
        if so.resolve() != dest.resolve():
            shutil.copy2(so, dest)
        print(f"built {dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
