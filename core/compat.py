"""macOS compatibility helpers — deployment targets, diagnostics, crash logs.

Why this module exists
----------------------
A PyInstaller bundle inherits the *minimum macOS version* baked into every
Mach-O file it ships: the Python framework, the Qt frameworks, CPython's
extension modules and any native library they link against.  dyld refuses to
load a library whose minimum version is newer than the running system, which
turns into the infamous silent crash ("the app does not start") on an older
macOS.  Building on a newer machine used to make the whole app depend on that
newer machine's OS without anybody noticing.

This module is deliberately dependency-free (stdlib only, no PyQt import at
module level) so that it can:
  * be imported before Qt loads (crash handler, ``--doctor``),
  * inspect a finished ``.app`` from the build script,
  * be exercised by the test-suite on any platform.

Public API
----------
``macho_slices(path)``      Mach-O architectures + LC_BUILD_VERSION per slice
``bundle_info(app)``        Info.plist + main executable of a ``.app``
``scan_bundle(app)``        every Mach-O file in the bundle, with its min macOS
``audit_bundle(app, ...)``  compare the bundle against a target macOS version
``collect_environment()``   runtime facts for ``PDFeverything --doctor``
``format_doctor(...)``      human-readable report
``install_crash_logging()`` faulthandler + excepthook into ~/Library/Logs
"""

from __future__ import annotations

import json
import os
import platform
import plistlib
import struct
import subprocess
import sys
import traceback
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

# ── Mach-O constants ────────────────────────────────────────────────────

MH_MAGIC = 0xFEEDFACE
MH_MAGIC_64 = 0xFEEDFACF
MH_CIGAM = 0xCEFAEDFE
MH_CIGAM_64 = 0xCFFAEDFE

FAT_MAGIC = 0xCAFEBABE          # bytes: CA FE BA BE
FAT_MAGIC_64 = 0xCAFEBABF
FAT_CIGAM = 0xBEBAFECA
FAT_CIGAM_64 = 0xBFBAFECA

LC_VERSION_MIN_MACOSX = 0x24
LC_BUILD_VERSION = 0x32
LC_LOAD_DYLIB = 0x0C
LC_LOAD_WEAK_DYLIB = 0x80000018
LC_REEXPORT_DYLIB = 0x8000001F
LC_LOAD_UPWARD_DYLIB = 0x80000023
DYLIB_COMMANDS = (LC_LOAD_DYLIB, LC_LOAD_WEAK_DYLIB,
                  LC_REEXPORT_DYLIB, LC_LOAD_UPWARD_DYLIB)
PLATFORM_MACOS = 1

CPU_ARCH_ABI64 = 0x01000000
CPU_TYPE_X86 = 7
CPU_TYPE_ARM = 12

_ARCH_NAMES = {
    CPU_TYPE_X86: "i386",
    CPU_TYPE_X86 | CPU_ARCH_ABI64: "x86_64",
    CPU_TYPE_ARM: "arm",
    CPU_TYPE_ARM | CPU_ARCH_ABI64: "arm64",
    0x0200000C: "arm64e",
}

# macOS 11 was the first release on Apple silicon; anything older is noise.
DEFAULT_MIN_MACOS = "13.0"


# ── version helpers ─────────────────────────────────────────────────────

def version_tuple(value: Any) -> Tuple[int, int, int]:
    """``"13.1"`` / ``"13.1.2"`` / ``13`` → ``(13, 1, 0)``.

    Tolerates ``None`` and junk (returns ``(0, 0, 0)``) because it is fed from
    Info.plist files written by humans.
    """
    if value is None:
        return (0, 0, 0)
    text = str(value).strip()
    if not text:
        return (0, 0, 0)
    parts: List[int] = []
    for chunk in text.split("."):
        digits = ""
        for ch in chunk:
            if ch.isdigit():
                digits += ch
            else:
                break
        if not digits:
            break
        parts.append(int(digits))
        if len(parts) == 3:
            break
    while len(parts) < 3:
        parts.append(0)
    return tuple(parts[:3])  # type: ignore[return-value]


def format_version(value: Tuple[int, int, int]) -> str:
    """``(13, 0, 0)`` → ``"13.0"``; keeps reports readable."""
    major, minor, patch = value
    return f"{major}.{minor}.{patch}" if patch else f"{major}.{minor}"


def _decode_version(raw: int) -> str:
    """Mach-O ``xxxx.yy.zz`` packed version → ``"13.0"``."""
    major = (raw >> 16) & 0xFFFF
    minor = (raw >> 8) & 0xFF
    patch = raw & 0xFF
    if patch:
        return f"{major}.{minor}.{patch}"
    return f"{major}.{minor}"


def running_macos_version() -> str:
    """Best-effort macOS version of the running system (``""`` off macOS)."""
    try:
        return platform.mac_ver()[0] or ""
    except Exception:
        return ""


# ── Mach-O parsing ──────────────────────────────────────────────────────

def _parse_thin(f, offset: int) -> Optional[Dict[str, Any]]:
    try:
        f.seek(offset)
        header = f.read(32)
    except OSError:
        return None
    if len(header) < 28:
        return None
    magic_le = struct.unpack("<I", header[:4])[0]
    if magic_le in (MH_MAGIC, MH_MAGIC_64):
        endian = "<"
        is64 = magic_le == MH_MAGIC_64
    elif magic_le in (MH_CIGAM, MH_CIGAM_64):
        endian = ">"
        is64 = magic_le == MH_CIGAM_64
    else:
        return None

    cputype, _cpusub = struct.unpack(endian + "ii", header[4:12])
    ncmds, sizeofcmds = struct.unpack(endian + "II", header[16:24])
    try:
        f.seek(offset + (32 if is64 else 28))
        commands = f.read(sizeofcmds)
    except OSError:
        return None

    minos = None
    sdk = None
    deps: List[str] = []
    pos = 0
    for _ in range(ncmds):
        if pos + 8 > len(commands):
            break
        cmd, cmdsize = struct.unpack_from(endian + "II", commands, pos)
        if cmdsize < 8:
            break
        if cmd == LC_BUILD_VERSION and pos + 24 <= len(commands):
            plat, minos_raw, sdk_raw = struct.unpack_from(
                endian + "III", commands, pos + 8
            )
            if plat == PLATFORM_MACOS:
                minos = _decode_version(minos_raw)
                sdk = _decode_version(sdk_raw)
        elif cmd == LC_VERSION_MIN_MACOSX and pos + 16 <= len(commands):
            minos_raw, sdk_raw = struct.unpack_from(endian + "II", commands, pos + 8)
            # 0.0.0 means "old linker, no information"; do not report it.
            if minos_raw:
                minos = _decode_version(minos_raw)
                sdk = _decode_version(sdk_raw)
        elif cmd in DYLIB_COMMANDS and pos + 12 <= len(commands):
            name_offset = struct.unpack_from(endian + "I", commands, pos + 8)[0]
            start = pos + name_offset
            end = commands.find(b"\0", start, pos + cmdsize)
            if start < len(commands) and end != -1:
                deps.append(commands[start:end].decode("utf-8", "replace"))
        pos += cmdsize

    return {
        "arch": _ARCH_NAMES.get(cputype, f"cpu{cputype}"),
        "minos": minos,
        "sdk": sdk,
        "deps": deps,
    }


def macho_slices(path: os.PathLike | str) -> List[Dict[str, Any]]:
    """Return ``[{"arch", "minos", "sdk"}, ...]`` for a Mach-O (fat or thin).

    Empty list for anything that is not a Mach-O file — callers use that to
    walk a bundle without maintaining an extension allow-list.
    """
    try:
        with open(path, "rb") as f:
            head = f.read(8)
            if len(head) < 8:
                return []
            raw = head[:4]
            if raw in (b"\xca\xfe\xba\xbe", b"\xca\xfe\xba\xbf"):
                # Fat header is always big-endian in practice, but tolerate LE.
                nfat = struct.unpack(">I", head[4:8])[0]
                if nfat > 64:  # sanity — corrupt file
                    return []
                entry_size = 20 if raw == b"\xca\xfe\xba\xbe" else 32
                table = f.read(nfat * entry_size)
                slices = []
                for i in range(nfat):
                    chunk = table[i * entry_size:(i + 1) * entry_size]
                    if len(chunk) < entry_size:
                        break
                    if entry_size == 20:
                        offset = struct.unpack_from(">I", chunk, 8)[0]
                    else:
                        offset = struct.unpack_from(">Q", chunk, 8)[0]
                    info = _parse_thin(f, offset)
                    if info:
                        slices.append(info)
                return slices
            if raw in (b"\xbe\xba\xfe\xca", b"\xbf\xba\xfe\xca"):
                nfat = struct.unpack("<I", head[4:8])[0]
                if nfat > 64:
                    return []
                entry_size = 20 if raw == b"\xbe\xba\xfe\xca" else 32
                table = f.read(nfat * entry_size)
                slices = []
                for i in range(nfat):
                    chunk = table[i * entry_size:(i + 1) * entry_size]
                    if len(chunk) < entry_size:
                        break
                    if entry_size == 20:
                        offset = struct.unpack_from("<I", chunk, 8)[0]
                    else:
                        offset = struct.unpack_from("<Q", chunk, 8)[0]
                    info = _parse_thin(f, offset)
                    if info:
                        slices.append(info)
                return slices
            info = _parse_thin(f, 0)
            return [info] if info else []
    except (OSError, ValueError, struct.error):
        return []


# ── bundle inspection ───────────────────────────────────────────────────

def bundle_info(app: os.PathLike | str) -> Dict[str, Any]:
    """Read the bits of ``Info.plist`` that matter for compatibility."""
    app_path = Path(app)
    info: Dict[str, Any] = {
        "path": str(app_path),
        "exists": app_path.exists(),
        "executable": None,
        "bundle_id": None,
        "short_version": None,
        "min_system": None,
    }
    plist_path = app_path / "Contents" / "Info.plist"
    if not plist_path.exists():
        return info
    try:
        with open(plist_path, "rb") as f:
            data = plistlib.load(f)
    except Exception:
        return info
    info["bundle_id"] = data.get("CFBundleIdentifier")
    info["short_version"] = data.get("CFBundleShortVersionString")
    info["min_system"] = data.get("LSMinimumSystemVersion")
    exe_name = data.get("CFBundleExecutable") or app_path.stem
    info["executable"] = str(app_path / "Contents" / "MacOS" / exe_name)
    return info


def _iter_bundle_files(app: Path) -> Iterable[Path]:
    for root, dirs, files in os.walk(app):
        # Skip obvious non-code trees to keep the scan fast.
        dirs[:] = [d for d in dirs if d not in ("__pycache__",)]
        for name in files:
            yield Path(root) / name


def scan_bundle(app: os.PathLike | str) -> List[Dict[str, Any]]:
    """Every Mach-O file inside ``app`` with its architecture(s) and min macOS.

    Symlinks are skipped (the target is scanned where it really lives) and so
    are files that are not Mach-O.
    """
    app_path = Path(app)
    entries: List[Dict[str, Any]] = []
    if not app_path.exists():
        return entries
    for path in _iter_bundle_files(app_path):
        if path.is_symlink() or not path.is_file():
            continue
        slices = macho_slices(path)
        if not slices:
            continue
        # Newest requirement wins: dyld rejects the bundle if *any* file
        # (or any slice of a fat file) needs a newer system than the host.
        newest = max(
            (version_tuple(s.get("minos")) for s in slices if s.get("minos")),
            default=(0, 0, 0),
        )
        external = sorted({
            dep for s in slices for dep in s.get("deps", [])
            if dep.startswith("/")
            and not dep.startswith(("/usr/lib/", "/System/"))
        })
        entries.append({
            "path": str(path.relative_to(app_path)),
            "archs": sorted({s["arch"] for s in slices}),
            "minos": format_version(newest) if newest != (0, 0, 0) else None,
            "slices": slices,
            "external_refs": external,
        })
    return entries


def effective_min_macos(entries: Iterable[Dict[str, Any]]) -> Tuple[str, Optional[Dict[str, Any]]]:
    """Highest ``minos`` across all scanned files, plus the file that has it."""
    best: Optional[Dict[str, Any]] = None
    best_tuple = (0, 0, 0)
    for entry in entries:
        value = entry.get("minos")
        if not value:
            continue
        tup = version_tuple(value)
        if tup > best_tuple:
            best_tuple = tup
            best = entry
    if best is None:
        return "", None
    return best["minos"], best


def _codesign_status(app: Path) -> Dict[str, Any]:
    """Signature facts. ``available`` is False when ``codesign`` is missing."""
    result: Dict[str, Any] = {
        "available": False,
        "valid": None,
        "signature": None,
        "authority": None,
        "hardened": False,
        "notarized_staple": False,
        "detail": "",
    }
    if sys.platform != "darwin":
        return result
    try:
        info = subprocess.run(
            ["codesign", "-dv", "--verbose=4", str(app)],
            capture_output=True, text=True, timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return result
    result["available"] = True
    text = (info.stderr or "") + (info.stdout or "")
    for line in text.splitlines():
        if line.startswith("Signature="):
            result["signature"] = line.split("=", 1)[1].strip()
        elif line.startswith("Authority=") and result["authority"] is None:
            result["authority"] = line.split("=", 1)[1].strip()
        elif "flags=" in line and "runtime" in line:
            result["hardened"] = True
    verify = subprocess.run(
        ["codesign", "--verify", "--deep", "--strict", str(app)],
        capture_output=True, text=True, timeout=120,
    )
    result["valid"] = verify.returncode == 0
    if verify.returncode != 0:
        result["detail"] = (verify.stderr or verify.stdout or "").strip()[:400]
    try:
        staple = subprocess.run(
            ["xcrun", "stapler", "validate", str(app)],
            capture_output=True, text=True, timeout=60,
        )
        result["notarized_staple"] = staple.returncode == 0
    except (OSError, subprocess.SubprocessError):
        pass
    return result


def quarantine_status(path: os.PathLike | str) -> Optional[str]:
    """Value of ``com.apple.quarantine`` if present, else ``None``."""
    if sys.platform != "darwin":
        return None
    try:
        out = subprocess.run(
            ["xattr", "-p", "com.apple.quarantine", str(path)],
            capture_output=True, text=True, timeout=15,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return (out.stdout or "").strip() or None


# ── audit ───────────────────────────────────────────────────────────────

def audit_bundle(
    app: os.PathLike | str,
    max_macos: str = DEFAULT_MIN_MACOS,
    arch: str = "arm64",
) -> Dict[str, Any]:
    """Check a built ``.app`` against a declared minimum macOS version.

    ``ok`` is False when
      * a bundled Mach-O requires a newer macOS than ``max_macos``,
      * the bundle does not contain the requested architecture,
      * ``LSMinimumSystemVersion`` claims an older system than the binaries can
        actually run on (the exact lie that shipped in 2.0.1: plist said 11.0
        while libpython required 26.0 / Homebrew's OpenSSL required 27.0),
      * the code signature is broken.
    """
    app_path = Path(app)
    target = version_tuple(max_macos)
    info = bundle_info(app_path)
    entries = scan_bundle(app_path)
    effective, worst = effective_min_macos(entries)

    offenders = [
        e for e in entries
        if e.get("minos") and version_tuple(e["minos"]) > target
    ]
    external = [
        {"path": e["path"], "dep": dep}
        for e in entries for dep in e.get("external_refs", [])
    ]
    offenders.sort(key=lambda e: version_tuple(e["minos"]), reverse=True)

    architectures = sorted({a for e in entries for a in e["archs"]})
    missing_arch = arch not in architectures if entries else True

    declared = info.get("min_system")
    declared_ok = version_tuple(declared) <= target if declared else False
    # The declared value may be *lower* than what the binaries need — that is
    # the "runs nowhere it claims to" bug — but a higher declared value is a
    # legitimate choice, so only flag the lying direction.
    declared_truthful = (
        version_tuple(declared) >= version_tuple(effective) if effective else True
    )

    signature = _codesign_status(app_path)
    quarantine = quarantine_status(app_path)

    problems: List[str] = []
    warnings: List[str] = []
    if not entries:
        problems.append("bundle contains no Mach-O executables (not a valid .app)")
    if missing_arch:
        problems.append(f"missing required architecture: {arch} (found: {architectures})")
    if offenders:
        problems.append(
            f"{len(offenders)} file(s) require a newer macOS than {max_macos}"
        )
    if external:
        problems.append(
            f"{len(external)} binary reference(s) point outside the bundle and "
            "outside the system (the app will not launch on a machine without "
            "that exact path)"
        )
    if declared and not declared_ok:
        problems.append(
            f"LSMinimumSystemVersion {declared} exceeds the build target {max_macos}"
        )
    if effective and not declared_truthful:
        problems.append(
            f"LSMinimumSystemVersion says {declared} but binaries need {effective} "
            "(app cannot launch on the systems it claims to support)"
        )
    if signature.get("available") and signature.get("valid") is False:
        problems.append("code signature is invalid")
    if signature.get("signature") == "adhoc" and not signature.get("notarized_staple"):
        warnings.append(
            "ad-hoc signature only — Gatekeeper blocks the downloaded app until "
            "the user allows it in System Settings (notarize for a clean first run)"
        )
    if quarantine:
        warnings.append("app carries the com.apple.quarantine attribute (downloaded copy)")

    return {
        "app": str(app_path),
        "target_macos": max_macos,
        "declared_macos": declared,
        "effective_macos": effective or None,
        "effective_from": worst["path"] if worst else None,
        "architectures": architectures,
        "file_count": len(entries),
        "offenders": [
            {"path": e["path"], "minos": e["minos"]} for e in offenders[:40]
        ],
        "offender_count": len(offenders),
        "external_refs": external[:40],
        "external_ref_count": len(external),
        "signature": signature,
        "quarantine": quarantine,
        "problems": problems,
        "warnings": warnings,
        "ok": not problems,
    }


def format_audit(report: Dict[str, Any]) -> str:
    lines = [
        f"Bundle      : {report['app']}",
        f"Architecture: {', '.join(report['architectures']) or '—'}",
        f"Target      : macOS {report['target_macos']}+",
        f"Declared    : LSMinimumSystemVersion={report['declared_macos']}",
        f"Effective   : macOS {report['effective_macos'] or '?'}+"
        + (f"  ({report['effective_from']})" if report.get("effective_from") else ""),
        f"Mach-O files: {report['file_count']}",
    ]
    sig = report.get("signature") or {}
    if sig.get("available"):
        lines.append(
            "Signature   : "
            + (sig.get("authority") or sig.get("signature") or "unknown")
            + (" [hardened]" if sig.get("hardened") else "")
            + ("" if sig.get("valid") else "  ✗ invalid")
        )
    if report.get("quarantine"):
        lines.append(f"Quarantine  : {report['quarantine']}")
    for warning in report.get("warnings", []):
        lines.append(f"WARN  {warning}")
    for problem in report.get("problems", []):
        lines.append(f"FAIL  {problem}")
    if report.get("external_refs"):
        lines.append("Binaries that reference paths outside the bundle:")
        for item in report["external_refs"][:20]:
            lines.append(f"  {item['dep']}  ({item['path']})")
    if report.get("offenders"):
        lines.append("Files that need a newer macOS:")
        for item in report["offenders"][:20]:
            lines.append(f"  {item['minos']:>6}  {item['path']}")
        if report["offender_count"] > len(report["offenders"]):
            lines.append(f"  … {report['offender_count'] - len(report['offenders'])} more")
    lines.append("RESULT: " + ("OK" if report.get("ok") else "FAILED"))
    return "\n".join(lines)


# ── runtime doctor ──────────────────────────────────────────────────────

def frozen_app_root() -> Optional[Path]:
    """``.../PDFeverything.app`` when running from a PyInstaller bundle."""
    if not getattr(sys, "frozen", False):
        return None
    exe = Path(sys.executable).resolve()
    for parent in exe.parents:
        if parent.suffix == ".app":
            return parent
    return None


def collect_environment(app: Optional[os.PathLike | str] = None) -> Dict[str, Any]:
    app_path = Path(app) if app else frozen_app_root()
    env: Dict[str, Any] = {
        "app": str(app_path) if app_path else None,
        "platform": sys.platform,
        "macos": running_macos_version(),
        "arch": platform.machine(),
        "python": sys.version.split()[0],
        "python_deployment_target": None,
        "frozen": bool(getattr(sys, "frozen", False)),
        "qt": None,
        "pyqt": None,
    }
    try:
        import sysconfig
        env["python_deployment_target"] = sysconfig.get_config_var(
            "MACOSX_DEPLOYMENT_TARGET"
        )
    except Exception:
        pass
    try:
        from PyQt6.QtCore import QT_VERSION_STR, PYQT_VERSION_STR  # type: ignore
        env["qt"] = QT_VERSION_STR
        env["pyqt"] = PYQT_VERSION_STR
    except Exception:
        pass
    # Native stdlib modules are the first casualty of a broken bundle: if the
    # linker could not find OpenSSL/zstd, these imports fail only at runtime.
    # Only probe modules that the bundle actually ships (`_sqlite3` is not
    # imported by the app, so its absence says nothing about the bundle).
    env["native_imports"] = {}
    import importlib
    import importlib.util
    for name, extension in (("ssl", "_ssl"), ("hashlib", "_hashlib"),
                            ("zlib", "zlib"), ("lzma", "_lzma"),
                            ("bz2", "_bz2"), ("sqlite3", "_sqlite3")):
        try:
            if importlib.util.find_spec(extension) is None:
                continue
            importlib.import_module(name)
            env["native_imports"][name] = True
        except Exception:
            env["native_imports"][name] = False
    if app_path and app_path.exists():
        info = bundle_info(app_path)
        # Doctor reports, it does not enforce: audit against whatever the bundle
        # declares, and against the architecture we are actually running.
        audit = audit_bundle(
            app_path,
            max_macos=info.get("min_system") or DEFAULT_MIN_MACOS,
            arch=platform.machine() or "arm64",
        )
        env["bundle"] = {
            key: audit[key]
            for key in ("declared_macos", "effective_macos", "architectures",
                        "signature", "quarantine", "ok", "problems", "warnings")
        }
    else:
        env["bundle"] = None
    return env


def format_doctor(env: Dict[str, Any]) -> str:
    lines = [
        "PDFeverything doctor",
        "────────────────────",
        f"macOS        : {env.get('macos') or '?'} ({env.get('arch')})",
        f"Python       : {env.get('python')}"
        + (f"  (built for macOS {env['python_deployment_target']}+)"
           if env.get("python_deployment_target") else ""),
        f"PyQt6 / Qt   : {env.get('pyqt') or '—'} / {env.get('qt') or '—'}",
        f"Frozen bundle: {'yes' if env.get('frozen') else 'no'}",
    ]
    bundle = env.get("bundle")
    if bundle:
        lines += [
            f"App bundle   : {env.get('app')}",
            f"Declared min : macOS {bundle.get('declared_macos')}",
            f"Effective min: macOS {bundle.get('effective_macos')}",
            f"Architectures: {', '.join(bundle.get('architectures') or [])}",
        ]
        signature = bundle.get("signature") or {}
        if signature.get("available"):
            lines.append(
                "Signature    : "
                + (signature.get("authority") or signature.get("signature") or "unknown")
                + ("  ✓ valid" if signature.get("valid") else "  ✗ invalid")
            )
        for warning in bundle.get("warnings") or []:
            lines.append(f"WARN  {warning}")
        for problem in bundle.get("problems") or []:
            lines.append(f"FAIL  {problem}")
    else:
        lines.append("App bundle   : — (running from source)")
    native = env.get("native_imports") or {}
    broken = [name for name, ok in native.items() if not ok]
    if native:
        lines.append("Native stdlib: " + ", ".join(
            f"{name} {'ok' if ok else 'FAILED'}" for name, ok in native.items()))
    for name in broken:
        lines.append(f"FAIL  native module '{name}' cannot be imported "
                     "(missing bundled library?)")
    return "\n".join(lines)


# ── crash logging ───────────────────────────────────────────────────────

_CRASH_STREAM = None  # keep the faulthandler file object alive


def log_dir() -> Path:
    base = Path.home() / "Library" / "Logs" / "PDFeverything"
    base.mkdir(parents=True, exist_ok=True)
    return base


def install_crash_logging() -> Optional[Path]:
    """Write uncaught exceptions and fatal signals to ``~/Library/Logs``.

    macOS GUI apps launched from Finder have no terminal, so a Python
    traceback used to vanish. Returns the log path (or ``None`` if the log
    directory cannot be created).
    """
    global _CRASH_STREAM
    try:
        path = log_dir() / "crash.log"
        stream = open(path, "a", encoding="utf-8", buffering=1)
    except OSError:
        return None
    _CRASH_STREAM = stream
    try:
        import faulthandler
        faulthandler.enable(file=stream, all_threads=True)
    except Exception:
        pass

    previous = sys.excepthook

    def _hook(exc_type, exc_value, exc_tb):
        try:
            stream.write("\n=== uncaught exception ===\n")
            stream.write("".join(traceback.format_exception(exc_type, exc_value, exc_tb)))
        except Exception:
            pass
        try:
            previous(exc_type, exc_value, exc_tb)
        except Exception:
            pass

    sys.excepthook = _hook
    return path


def show_native_alert(title: str, message: str) -> None:
    """Last-resort dialog that works even when Qt failed to initialise."""
    if sys.platform != "darwin":
        return
    safe_title = title.replace("\\", "\\\\").replace('"', '\\"')
    safe_message = message.replace("\\", "\\\\").replace('"', '\\"')
    script = (
        f'display alert "{safe_title}" message "{safe_message}" '
        'as critical buttons {"OK"} default button "OK"'
    )
    try:
        subprocess.run(["osascript", "-e", script], capture_output=True, timeout=60)
    except (OSError, subprocess.SubprocessError):
        pass


# ── CLI ─────────────────────────────────────────────────────────────────

def _main(argv: Optional[List[str]] = None) -> int:
    import argparse
    parser = argparse.ArgumentParser(
        prog="python -m core.compat",
        description="Audit a macOS .app bundle's minimum system version.",
    )
    parser.add_argument("app", nargs="?", help="path to PDFeverything.app")
    parser.add_argument("--max-macos", default=DEFAULT_MIN_MACOS,
                        help=f"highest allowed deployment target (default {DEFAULT_MIN_MACOS})")
    parser.add_argument("--arch", default="arm64", help="required architecture")
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    parser.add_argument("--doctor", action="store_true",
                        help="print the runtime environment instead of auditing a bundle")
    args = parser.parse_args(argv)

    if args.doctor:
        env = collect_environment(args.app)
        if args.json:
            print(json.dumps(env, indent=2, ensure_ascii=False))
        else:
            print(format_doctor(env))
        return 0

    if not args.app:
        parser.error("an .app path is required (or use --doctor)")
    report = audit_bundle(args.app, max_macos=args.max_macos, arch=args.arch)
    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        print(format_audit(report))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(_main())
