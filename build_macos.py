#!/usr/bin/env python3
"""Build PDFeverything.app for macOS — portable, audited, signed, optional notarization.

Why a script instead of a bare ``pyinstaller`` call
---------------------------------------------------
A bundle inherits the deployment target of *every* Mach-O it contains.  Building
on a new macOS with a Python (or Qt, or a wheel) that targets that new macOS
silently produces an app that cannot start on older systems — the exact cause of
issue #1 ("不能在 macOS 26 上运行": libpython required 26.0 and Homebrew's
OpenSSL required 27.0 while Info.plist promised 11.0).

This script fails the build *before* packaging when the toolchain is too new, and
audits the finished bundle afterwards.  It is the only supported macOS build path.

Usage
-----
    python build_macos.py                       # arm64, macOS 13+, ad-hoc signed
    python build_macos.py --min-macos 13.0
    python build_macos.py --identity -          # explicit ad-hoc (default)
    python build_macos.py --identity "Developer ID Application: Name (TEAMID)" \
                          --notarize --keychain-profile pdfeverything
    python build_macos.py --check-only          # audit dist/PDFeverything.app

Requirements for a portable build
---------------------------------
* Python from python.org (``python-3.14.0-macos11.pkg`` or newer) — the
  framework is built for macOS 11.0.  Homebrew/pyenv Pythons inherit the host
  deployment target and are **not** portable.
* PyQt6 6.11.x  — Qt 6.11 targets macOS 13.0; 6.12 raises the bar to 14.4.
"""

from __future__ import annotations

import argparse
import os
import platform
import plistlib
import shutil
import subprocess
import sys
import sysconfig
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
APP_NAME = "PDFeverything"
SPEC = PROJECT_ROOT / "PDFeverything.spec"
APP_PATH = PROJECT_ROOT / "dist" / f"{APP_NAME}.app"
ENTITLEMENTS = PROJECT_ROOT / "resources" / "macos_entitlements.plist"

sys.path.insert(0, str(PROJECT_ROOT))
from core.compat import (  # noqa: E402
    DEFAULT_MIN_MACOS,
    audit_bundle,
    effective_min_macos,
    format_audit,
    format_version,
    macho_slices,
    scan_bundle,
    version_tuple,
)

# PyQt6 6.11 is the newest series that still supports macOS 13.  A newer Qt
# silently raises the floor (6.12 = macOS 14.4), so name the reason here and in
# the requirements file.
KNOWN_QT_FLOORS = {
    (6, 12): "14.4",
}


class BuildError(RuntimeError):
    pass


def run(cmd: list[str], *, env: dict | None = None, check: bool = True,
        capture: bool = False) -> subprocess.CompletedProcess:
    printable = " ".join(str(c) for c in cmd)
    print(f"  $ {printable}")
    return subprocess.run(
        cmd, env=env, check=check,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.STDOUT if capture else None,
        text=True,
    )


# ── preflight ───────────────────────────────────────────────────────────

def _max_minos_in(path: Path) -> tuple[str, str | None]:
    entries = scan_bundle(path)
    return effective_min_macos(entries)


def preflight(min_macos: str, arch: str) -> None:
    print("Preflight")
    if sys.platform != "darwin":
        raise BuildError("macOS is required to build the .app bundle")

    target = version_tuple(min_macos)
    if target < version_tuple("11.0"):
        raise BuildError("macOS 11 is the oldest release that runs on Apple silicon")

    python_target = sysconfig.get_config_var("MACOSX_DEPLOYMENT_TARGET") or "0"
    print(f"  Python {platform.python_version()} "
          f"({platform.machine()}), deployment target macOS {python_target}")
    if version_tuple(python_target) > target:
        raise BuildError(
            f"this Python is built for macOS {python_target}+ but the bundle "
            f"promises macOS {min_macos}+.\n"
            "  Every binary compiled against it (libpython, extension modules) "
            "would make the app unlaunchable on older systems.\n"
            "  Use the python.org universal2 installer "
            "(python-3.14.0-macos11.pkg), not Homebrew/pyenv, "
            "or raise --min-macos (not recommended)."
        )

    slices = macho_slices(sys.executable)
    python_archs = {s["arch"] for s in slices}
    if arch == "arm64" and "arm64" not in python_archs:
        raise BuildError(f"Python has no arm64 slice (found {sorted(python_archs)})")
    if arch == "universal2" and not {"arm64", "x86_64"} <= python_archs:
        raise BuildError(
            f"universal2 needs a universal2 Python (found {sorted(python_archs)})"
        )

    try:
        import PyQt6
        from PyQt6.QtCore import PYQT_VERSION_STR, QT_VERSION_STR
    except ImportError as exc:
        raise BuildError(f"PyQt6 is not installed in this interpreter: {exc}") from exc
    qt_min, worst = _max_minos_in(Path(PyQt6.__file__).parent)
    print(f"  PyQt6 {PYQT_VERSION_STR} / Qt {QT_VERSION_STR}: needs macOS {qt_min}+"
          + (f"  ({worst})" if worst else ""))
    if version_tuple(qt_min) > target:
        raise BuildError(
            f"the installed PyQt6/Qt requires macOS {qt_min}+, "
            f"above --min-macos {min_macos}.\n"
            "  Pin PyQt6 6.11.x (see requirements.txt) or raise --min-macos."
        )

    try:
        import PyInstaller  # noqa: F401
        print(f"  PyInstaller {PyInstaller.__version__}")
    except ImportError as exc:
        raise BuildError("PyInstaller is not installed in this interpreter") from exc

    for name, modules in (("pymupdf", ("pymupdf", "fitz")),
                          ("cryptography", ("cryptography",)),
                          ("PIL", ("PIL",))):
        package_dir = None
        for module in modules:
            try:
                mod = __import__(module)
            except Exception as exc:  # noqa: BLE001 - report, don't crash
                raise BuildError(f"{name} is not importable: {exc}") from exc
            candidate = Path(mod.__file__).parent
            # fitz is a shim; the native code lives next to it in pymupdf/
            if _max_minos_in(candidate)[0]:
                package_dir = candidate
                break
            package_dir = package_dir or candidate
        dep_min, dep_worst = _max_minos_in(package_dir) if package_dir else ("", None)
        print(f"  {name}: needs macOS {dep_min or '?'}+"
              + (f"  ({dep_worst})" if dep_worst else ""))
        if dep_min and version_tuple(dep_min) > target:
            raise BuildError(
                f"{name} requires macOS {dep_min}+ ({dep_worst}), "
                f"above --min-macos {min_macos}.\n"
                "  Install an older wheel whose binaries target a lower system."
            )


# ── build ───────────────────────────────────────────────────────────────

def build(min_macos: str, arch: str, identity: str | None) -> None:
    env = dict(os.environ)
    env["PYINSTALLER_CONFIG_DIR"] = str(PROJECT_ROOT / ".buildcache")
    env["MACOSX_DEPLOYMENT_TARGET"] = min_macos
    env["PDFE_MIN_MACOS"] = min_macos
    env["PDFE_TARGET_ARCH"] = arch
    env["PDFE_CODESIGN_IDENTITY"] = identity or ""

    shutil.rmtree(PROJECT_ROOT / "build", ignore_errors=True)
    print("\nPyInstaller")
    run([sys.executable, "-m", "PyInstaller", str(SPEC), "--noconfirm", "--clean"],
        env=env)
    if not APP_PATH.exists():
        raise BuildError(f"PyInstaller did not produce {APP_PATH}")


def sign(app: Path, identity: str | None, notarize: bool) -> None:
    """Sign inside-out.  Ad-hoc is enough for local use; Developer ID for distribution."""
    identity = identity or "-"
    print("\nCode signing")
    if identity == "-":
        run(["codesign", "--force", "--deep", "--sign", "-", str(app)])
    else:
        entitlements_arg = ["--entitlements", str(ENTITLEMENTS)]
        # Nested code first (deepest paths first), then the bundle itself.
        nested: list[Path] = []
        for path in app.rglob("*"):
            if path.is_symlink() or not path.is_file():
                continue
            if path == app / "Contents" / "MacOS" / APP_NAME:
                continue
            if path.suffix in (".dylib", ".so") or macho_slices(path):
                nested.append(path)
        nested.sort(key=lambda p: len(p.parts), reverse=True)
        for path in nested:
            run(["codesign", "--force", "--options", "runtime", "--timestamp",
                 "--sign", identity, str(path)])
        run(["codesign", "--force", "--options", "runtime", "--timestamp",
             *entitlements_arg, "--sign", identity, str(app)])
    run(["codesign", "--verify", "--deep", "--strict", "--verbose=2", str(app)])
    if notarize and identity == "-":
        raise BuildError("--notarize needs a Developer ID identity, not ad-hoc")


def notarize(app: Path, archive: Path, profile: str) -> None:
    print("\nNotarization")
    run(["xcrun", "notarytool", "submit", str(archive),
         "--keychain-profile", profile, "--wait"])
    run(["xcrun", "stapler", "staple", str(app)])
    run(["xcrun", "stapler", "validate", str(app)])


# ── package ─────────────────────────────────────────────────────────────

def _scrub_quarantine(app: Path) -> None:
    subprocess.run(["xattr", "-cr", str(app)], check=False)


def package(app: Path, version: str) -> tuple[Path, str]:
    print("\nPackaging")
    _scrub_quarantine(app)
    archive = Path("/tmp") / f"PDFeverything_macOS_v{version}.zip"
    archive.unlink(missing_ok=True)
    run(["ditto", "-c", "-k", "--sequesterRsrc", "--keepParent",
         str(app), str(archive)])
    digest = subprocess.run(["shasum", "-a", "256", str(archive)],
                            capture_output=True, text=True, check=True).stdout.split()[0]
    print(f"  {archive}  ({archive.stat().st_size / 1e6:.1f} MB)")
    print(f"  SHA-256 {digest}")
    return archive, digest


def app_version() -> str:
    with open(APP_PATH / "Contents" / "Info.plist", "rb") as f:
        return plistlib.load(f).get("CFBundleShortVersionString", "0.0.0")


# ── main ────────────────────────────────────────────────────────────────

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build and audit a portable PDFeverything.app",
    )
    parser.add_argument("--min-macos", default=os.environ.get("PDFE_MIN_MACOS",
                                                             DEFAULT_MIN_MACOS),
                        help=f"minimum supported macOS (default {DEFAULT_MIN_MACOS})")
    parser.add_argument("--arch", default=os.environ.get("PDFE_TARGET_ARCH", "arm64"),
                        choices=("arm64", "universal2", "x86_64"))
    parser.add_argument("--identity", default=os.environ.get("PDFE_CODESIGN_IDENTITY"),
                        help='codesign identity; omit or "-" for ad-hoc')
    parser.add_argument("--notarize", action="store_true",
                        help="submit to Apple notary service (needs --identity and "
                             "--keychain-profile)")
    parser.add_argument("--keychain-profile", default="pdfeverything",
                        help="notarytool keychain profile name")
    parser.add_argument("--no-zip", action="store_true", help="skip zip packaging")
    parser.add_argument("--check-only", action="store_true",
                        help="audit dist/PDFeverything.app and exit")
    args = parser.parse_args(argv)

    started = time.time()
    if args.check_only:
        report = audit_bundle(APP_PATH, max_macos=args.min_macos, arch=args.arch)
        print(format_audit(report))
        return 0 if report["ok"] else 1

    try:
        preflight(args.min_macos, args.arch)
        build(args.min_macos, args.arch, args.identity)
        sign(APP_PATH, args.identity, args.notarize)
    except (BuildError, subprocess.CalledProcessError) as exc:
        print(f"\nBUILD FAILED: {exc}", file=sys.stderr)
        return 2

    print("\nAudit")
    report = audit_bundle(APP_PATH, max_macos=args.min_macos, arch=args.arch)
    print(format_audit(report))
    if not report["ok"]:
        print("\nThe bundle does not meet the declared compatibility target.",
              file=sys.stderr)
        return 3

    archive = digest = None
    if not args.no_zip:
        archive, digest = package(APP_PATH, app_version())
    if args.notarize:
        if archive is None:
            archive, digest = package(APP_PATH, app_version())
        notarize(APP_PATH, archive, args.keychain_profile)

    print(f"\nDone in {time.time() - started:.1f}s — "
          f"effective minimum macOS {report['effective_macos']} "
          f"({', '.join(report['architectures'])})")
    if archive:
        print(f"Artifact: {archive}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
