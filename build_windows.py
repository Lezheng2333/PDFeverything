#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PDFeverything — Windows onefile build script
Usage: python build_windows.py
Output: dist/PDFeverything.exe (single file, copy-and-run)
"""

import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

PROJECT_DIR = Path(__file__).parent.resolve()
DIST_DIR = PROJECT_DIR / "dist"
BUILD_DIR = PROJECT_DIR / "build"
OUTPUT_EXE = DIST_DIR / "PDFeverything.exe"
SPEC_FILE = PROJECT_DIR / "build_windows.spec"
REQUIREMENTS = [
    "PyQt6", "PyMuPDF", "pypdf", "pikepdf", "pillow",
    "python-docx", "python-pptx", "openpyxl", "pywin32", "pyinstaller",
]


def print_banner():
    print()
    print("=" * 60)
    print("    PDFeverything - Windows Build Script")
    print("=" * 60)
    print()


def step(msg):
    print(f"\n>>> {msg}")


def ok(msg=""):
    print(f"    [OK] {msg}")


def fail(msg):
    print(f"\n{'='*60}")
    print(f"  [FAILED] {msg}")
    print(f"{'='*60}")
    print()
    input("Press Enter to exit...")
    sys.exit(1)


def run(cmd, timeout=600, cwd=None):
    if cwd is None:
        cwd = str(PROJECT_DIR)
    print(f"    $ {' '.join(cmd[:5])}{'...' if len(cmd) > 5 else ''}")
    try:
        proc = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding="utf-8", errors="replace", cwd=cwd,
        )
        last_print = time.time()
        for line in proc.stdout:
            line = line.rstrip()
            now = time.time()
            if now - last_print > 2 or "error" in line.lower() or "warning" in line.lower():
                print(f"      {line[:120]}")
                last_print = now
        proc.wait(timeout=timeout)
        return proc.returncode
    except subprocess.TimeoutExpired:
        proc.kill()
        print(f"    Timeout ({timeout}s)")
        return -1
    except Exception as e:
        print(f"    Exception: {e}")
        return -1


# ── Steps ──

def step1():
    step("Step 1/4 - Check Python")
    v = sys.version_info
    print(f"    Python {v.major}.{v.minor}.{v.micro}")
    if v < (3, 10):
        fail("Python 3.10+ required. Download from python.org")
    ok()


def step2():
    step("Step 2/4 - Install dependencies")
    for pkg in REQUIREMENTS:
        print(f"    Installing {pkg}...")
        rc = run([sys.executable, "-m", "pip", "install", "--upgrade", pkg, "--quiet"])
        if rc != 0:
            print(f"    Retrying {pkg} with verbose output...")
            rc2 = run([sys.executable, "-m", "pip", "install", pkg])
            if rc2 != 0:
                fail(f"Failed to install {pkg}. Check network.")
    ok("All dependencies installed")


def step3():
    step("Step 3/4 - Clean old build")
    for d in [BUILD_DIR, OUTPUT_EXE]:
        try:
            if d.is_dir():
                shutil.rmtree(d)
                print(f"    Deleted: {d}")
            elif d.is_file():
                d.unlink()
                print(f"    Deleted: {d}")
        except Exception as e:
            print(f"    Warning: {e}")
    ok()


def step4():
    step("Step 4/4 - PyInstaller onefile build (3-10 min)")
    print("    If antivirus pops up, click Allow.")
    print()
    rc = run(
        [sys.executable, "-m", "PyInstaller",
         str(SPEC_FILE), "--noconfirm", "--clean", "--log-level", "WARN"],
        timeout=1200,
    )
    if rc != 0:
        fail("PyInstaller failed. Check antivirus or disk space.")
    if not OUTPUT_EXE.exists():
        fail(f"Output not found: {OUTPUT_EXE}")
    size_mb = OUTPUT_EXE.stat().st_size / 1024 / 1024
    print(f"    File size: {size_mb:.1f} MB")
    ok("Build complete")


def finish():
    size_mb = OUTPUT_EXE.stat().st_size / 1024 / 1024
    print()
    print("=" * 60)
    print("           Build Successful!")
    print("=" * 60)
    print()
    print(f"  Output: {OUTPUT_EXE}")
    print(f"  Size:   {size_mb:.1f} MB")
    print()
    print("  Copy PDFeverything.exe to any Windows PC.")
    print("  Double-click to run. No install needed.")
    print()
    print("=" * 60)
    try:
        os.startfile(str(DIST_DIR))
    except Exception:
        pass
    input("\nPress Enter to exit...")


def main():
    print_banner()
    step1()
    step2()
    step3()
    step4()
    finish()


if __name__ == "__main__":
    main()
