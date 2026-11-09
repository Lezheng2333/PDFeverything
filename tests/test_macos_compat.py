"""macOS portability regression suite — Mach-O parsing, bundle audit, doctor.

Run:  .venv/bin/python tests/test_macos_compat.py
Exit code 0 = all green.  No Qt, no display, no .app required.

These tests exist because 2.0.1 shipped a bundle that claimed macOS 11.0 while
its libpython required 26.0 and Homebrew's OpenSSL required 27.0 — the app
could not start on macOS 26 (issue #1).  The audit must catch that class of bug
before anything is uploaded.
"""

import os
import plistlib
import struct
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from core import compat  # noqa: E402

RESULTS = []


def check(name, condition, detail=""):
    RESULTS.append((name, bool(condition), detail))
    mark = "✅" if condition else "❌"
    print(f"  {mark} {name}" + (f"  — {detail}" if detail and not condition else ""))


# ── synthetic Mach-O helpers ────────────────────────────────────────────

ARM64 = 0x0100000C
X86_64 = 0x01000007


def fake_macho(minos="13.0", cputype=ARM64, deps=()):
    """Minimal 64-bit Mach-O: LC_BUILD_VERSION plus LC_LOAD_DYLIB entries."""
    parts = [int(x) for x in (minos.split(".") + ["0", "0"])[:3]]
    packed = (parts[0] << 16) | (parts[1] << 8) | parts[2]
    commands = [struct.pack("<IIIIII", 0x32, 24, 1, packed, packed, 0)]
    for dep in deps:
        raw = dep.encode() + b"\0"
        size = 24 + len(raw)
        size += (-size) % 8
        commands.append(
            struct.pack("<IIIIII", 0x0C, size, 24, 0, 0x10000, 0x10000)
            + raw
            + b"\0" * (size - 24 - len(raw))
        )
    body = b"".join(commands)
    header = struct.pack(
        "<IiiIIIII", 0xFEEDFACF, cputype, 0, 2, len(commands), len(body), 0, 0
    )
    return header + body


def fake_fat(*slices):
    """Fat binary wrapping ``(offset, thin_bytes)`` pairs."""
    header = struct.pack(">II", 0xCAFEBABE, len(slices))
    table = b""
    for offset, payload in slices:
        table += struct.pack(">iiIII", ARM64, 0, offset, len(payload), 12)
    body = header + table
    for offset, payload in slices:
        body = body.ljust(offset, b"\0") + payload
    return body


def make_app(root: Path, files: dict, min_system="13.0", exe="Test"):
    """Create a minimal ``X.app`` with the given ``relative path -> bytes``."""
    app = root / "Test.app"
    (app / "Contents" / "MacOS").mkdir(parents=True, exist_ok=True)
    info = {
        "CFBundleIdentifier": "com.example.test",
        "CFBundleExecutable": exe,
        "CFBundleShortVersionString": "9.9.9",
        "LSMinimumSystemVersion": min_system,
    }
    with open(app / "Contents" / "Info.plist", "wb") as f:
        plistlib.dump(info, f)
    for rel, payload in files.items():
        target = app / "Contents" / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(payload)
    return app


def no_signature(app):
    return {"available": False, "valid": None, "signature": None, "authority": None,
            "hardened": False, "notarized_staple": False, "detail": ""}


# ═══════════════════════════════════════════════════════════
print("\n═══ 1. Version helpers ═══")

check("version_tuple plain major", compat.version_tuple("13") == (13, 0, 0))
check("version_tuple two parts", compat.version_tuple("13.1") == (13, 1, 0))
check("version_tuple three parts", compat.version_tuple("14.2.1") == (14, 2, 1))
check("version_tuple tolerates junk", compat.version_tuple("abc") == (0, 0, 0))
check("version_tuple tolerates None", compat.version_tuple(None) == (0, 0, 0))
check("format_version drops zero patch", compat.format_version((27, 0, 0)) == "27.0")
check("format_version keeps patch", compat.format_version((13, 1, 2)) == "13.1.2")

# ═══════════════════════════════════════════════════════════
print("\n═══ 2. Mach-O parsing ═══")

with tempfile.TemporaryDirectory() as tmp:
    tmp = Path(tmp)

    thin = tmp / "thin"
    thin.write_bytes(fake_macho("13.0"))
    slices = compat.macho_slices(thin)
    check("thin Mach-O parsed", len(slices) == 1, repr(slices))
    check("thin architecture decoded", slices and slices[0]["arch"] == "arm64")
    check("thin deployment target decoded", slices and slices[0]["minos"] == "13.0")
    check("thin sdk decoded", slices and slices[0]["sdk"] == "13.0")

    fat = tmp / "fat"
    fat.write_bytes(fake_fat((4096, fake_macho("11.0")), (8192, fake_macho("14.4", X86_64))))
    fat_slices = compat.macho_slices(fat)
    check("fat Mach-O lists both slices", len(fat_slices) == 2, repr(fat_slices))
    check("fat arm64 slice minos", {s["minos"] for s in fat_slices} == {"11.0", "14.4"},
          repr(fat_slices))

    junk = tmp / "junk.txt"
    junk.write_bytes(b"not a mach-o at all")
    check("non Mach-O returns empty", compat.macho_slices(junk) == [])

    linked = tmp / "linked"
    linked.write_bytes(fake_macho("13.0", deps=[
        "@rpath/libQtCore.6.dylib",
        "/usr/lib/libSystem.B.dylib",
        "/opt/homebrew/lib/libfoo.1.dylib",
    ]))
    linked_slices = compat.macho_slices(linked)
    check("dylib load commands parsed",
          len(linked_slices[0].get("deps", [])) == 3, repr(linked_slices))

# ═══════════════════════════════════════════════════════════
print("\n═══ 3. Bundle audit ═══")

_original_signature = compat._codesign_status
compat._codesign_status = no_signature  # deterministic: no codesign in tests

try:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)

        good = make_app(root / "good", {"MacOS/Test": fake_macho("13.0")},
                        min_system="13.0")
        os.makedirs(root / "good", exist_ok=True)
        report = compat.audit_bundle(good, "13.0", "arm64")
        check("clean bundle passes", report["ok"] is True, str(report["problems"]))
        check("clean bundle effective min", report["effective_macos"] == "13.0")
        check("clean bundle declared min", report["declared_macos"] == "13.0")
        check("clean bundle arch detected", report["architectures"] == ["arm64"])

        bad = make_app(root / "bad", {
            "MacOS/Test": fake_macho("11.0"),
            "Frameworks/libcrypto.3.dylib": fake_macho("27.0"),
            "Frameworks/libpython3.14.dylib": fake_macho("26.0"),
        }, min_system="11.0")
        os.makedirs(root / "bad", exist_ok=True)
        report = compat.audit_bundle(bad, "13.0", "arm64")
        check("newer-than-target bundle fails", report["ok"] is False)
        check("offenders counted", report["offender_count"] == 2,
              str(report["offender_count"]))
        check("effective min is the newest offender",
              report["effective_macos"] == "27.0", report["effective_macos"])
        check("offender path reported",
              any(o["path"].endswith("libcrypto.3.dylib") for o in report["offenders"]))
        check("lying Info.plist detected",
              any("cannot launch" in p for p in report["problems"]),
              str(report["problems"]))
        text = compat.format_audit(report)
        check("formatted report says FAILED", "RESULT: FAILED" in text)
        check("formatted report names the offender", "libcrypto.3.dylib" in text)

        wrong_arch = make_app(root / "x86", {"MacOS/Test": fake_macho("13.0", X86_64)},
                              min_system="13.0")
        os.makedirs(root / "x86", exist_ok=True)
        report = compat.audit_bundle(wrong_arch, "13.0", "arm64")
        check("missing architecture fails",
              any("missing required architecture" in p for p in report["problems"]),
              str(report["problems"]))

        missing = compat.audit_bundle(root / "does-not-exist.app", "13.0")
        check("missing bundle fails cleanly", missing["ok"] is False)

        external = make_app(root / "external", {
            "MacOS/Test": fake_macho("13.0", deps=[
                "@rpath/QtCore",
                "/usr/lib/libSystem.B.dylib",
                "/opt/homebrew/lib/libssl.3.dylib",
            ]),
        }, min_system="13.0")
        os.makedirs(root / "external", exist_ok=True)
        report = compat.audit_bundle(external, "13.0", "arm64")
        check("external dylib reference fails",
              any("outside the bundle" in p for p in report["problems"]),
              str(report["problems"]))
        check("only the non-system reference is flagged",
              [r["dep"] for r in report["external_refs"]]
              == ["/opt/homebrew/lib/libssl.3.dylib"],
              repr(report["external_refs"]))
        check("external reference named in report",
              "libssl.3.dylib" in compat.format_audit(report))
finally:
    compat._codesign_status = _original_signature

# ═══════════════════════════════════════════════════════════
print("\n═══ 4. Runtime doctor ═══")

env = compat.collect_environment(app=None)
check("doctor reports python version", bool(env.get("python")))
check("doctor reports platform", env.get("platform") == sys.platform)
check("doctor reports architecture", env.get("arch") == compat.platform.machine())
check("doctor tolerates no bundle", env.get("bundle") is None)
text = compat.format_doctor(env)
check("doctor text has header", "PDFeverything doctor" in text)
check("doctor text mentions macOS", "macOS" in text)

if sys.platform == "darwin":
    check("running macOS version detected", bool(compat.running_macos_version()),
          compat.running_macos_version())
    real = compat.macho_slices(sys.executable)
    check("real interpreter parses as Mach-O", bool(real), repr(real))
    check("real interpreter has a deployment target",
          all(s.get("minos") for s in real), repr(real))

# ═══════════════════════════════════════════════════════════
passed = sum(1 for _, ok, _ in RESULTS if ok)
total = len(RESULTS)
print("\n" + "=" * 56)
print(f"  {passed}/{total} passed" + (" ✅" if passed == total else " ❌"))
print("=" * 56)
for name, ok, detail in RESULTS:
    if not ok:
        print(f"  FAILED: {name} — {detail}")
sys.exit(0 if passed == total else 1)
