#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PDFeverything — Windows 构建脚本
================================
用法:
    python build_windows.py                # 装依赖 → 打包 exe → 打成安装包
    python build_windows.py --skip-deps    # 依赖已就绪时跳过 pip（CI 用）
    python build_windows.py --exe-only     # 只要免安装 exe，不生成安装包

产物:
    dist/PDFeverything.exe                  单文件免安装版（安装包的载荷）
    dist/PDFeverything_Setup_v<ver>.exe     Windows 安装包
    PDFeverything_Setup_v<ver>.exe          安装包副本（项目根目录，直接分发）

安装包由 Inno Setup 6 编译（installer_windows.iss）。未安装 Inno Setup 时
构建照常完成，只是跳过安装包那一步并给出提示。
"""

import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

# 英文版 Windows 控制台是 cp437/cp1252，打印中文会抛 UnicodeEncodeError 把
# 一次成功的构建判成失败。保留原编码，只把不可编码字符降级为 "?"。
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(errors="replace")
    except Exception:
        pass

PROJECT_DIR = Path(__file__).parent.resolve()
DIST_DIR = PROJECT_DIR / "dist"
BUILD_DIR = PROJECT_DIR / "build"
OUTPUT_EXE = DIST_DIR / "PDFeverything.exe"
SPEC_FILE = PROJECT_DIR / "build_windows.spec"
ISS_FILE = PROJECT_DIR / "installer_windows.iss"
REQUIREMENTS = [
    "PyQt6", "PyMuPDF", "pypdf", "pikepdf", "pillow",
    "python-docx", "python-pptx", "openpyxl", "pywin32", "pyinstaller",
]

SKIP_DEPS = "--skip-deps" in sys.argv
EXE_ONLY = "--exe-only" in sys.argv
TOTAL_STEPS = 4 if EXE_ONLY else 5


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


def pause(prompt="Press Enter to exit..."):
    """CI 里没有 TTY，input() 会抛 EOFError 把成功的构建判成失败。"""
    if os.environ.get("PDFEVERYTHING_NO_PAUSE") or not sys.stdin.isatty():
        return
    try:
        input(prompt)
    except (EOFError, KeyboardInterrupt):
        pass


def fail(msg):
    print(f"\n{'='*60}")
    print(f"  [FAILED] {msg}")
    print(f"{'='*60}")
    print()
    pause()
    sys.exit(1)


def run(cmd, timeout=600, cwd=None):
    if cwd is None:
        cwd = str(PROJECT_DIR)
    print(f"    $ {' '.join(str(c) for c in cmd[:5])}{'...' if len(cmd) > 5 else ''}")
    try:
        proc = subprocess.Popen(
            [str(c) for c in cmd], stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding="utf-8", errors="replace", cwd=cwd,
        )
        last_print = time.time()
        for line in proc.stdout:
            line = line.rstrip()
            now = time.time()
            important = "error" in line.lower() or "warning" in line.lower()
            if important or now - last_print > 2:
                # 报错/告警行绝不截断：上次 Inno Setup 的失败信息被这里的 [:120]
                # 切掉，只看到 'Couldn\'t open include file "c:\program files'，
                # 白跑一轮 CI 才知道缺的是哪个文件。
                print(f"      {line if important else line[:120]}")
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


def read_version():
    """版本号只在 main.py 里定义一次，这里读它，避免两处写死不一致。"""
    try:
        text = (PROJECT_DIR / "main.py").read_text(encoding="utf-8")
        m = re.search(r'^VERSION\s*=\s*"([^"]+)"', text, re.M)
        if m:
            return m.group(1)
    except Exception as e:
        print(f"    Warning: 读取版本号失败 ({e})")
    return "0.0.0"


def find_iscc():
    """按 PATH → ISCC 环境变量 → 默认安装目录的顺序找 Inno Setup 编译器。"""
    env_iscc = os.environ.get("ISCC")
    if env_iscc and Path(env_iscc).is_file():
        return Path(env_iscc)
    on_path = shutil.which("ISCC") or shutil.which("iscc")
    if on_path:
        return Path(on_path)
    for base in (os.environ.get("ProgramFiles(x86)"), os.environ.get("ProgramFiles")):
        if base:
            candidate = Path(base) / "Inno Setup 6" / "ISCC.exe"
            if candidate.is_file():
                return candidate
    return None


# ── Steps ──

def step1():
    step(f"Step 1/{TOTAL_STEPS} - Check Python")
    v = sys.version_info
    print(f"    Python {v.major}.{v.minor}.{v.micro}")
    if v < (3, 10):
        fail("Python 3.10+ required. Download from python.org")
    ok()


def step2():
    step(f"Step 2/{TOTAL_STEPS} - Install dependencies")
    if SKIP_DEPS:
        print("    Skipped (--skip-deps)")
        ok()
        return
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
    step(f"Step 3/{TOTAL_STEPS} - Clean old build")
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
    if not EXE_ONLY:
        for old in DIST_DIR.glob("PDFeverything_Setup_v*.exe"):
            try:
                old.unlink()
                print(f"    Deleted: {old}")
            except Exception as e:
                print(f"    Warning: {e}")
    ok()


def step4():
    step(f"Step 4/{TOTAL_STEPS} - PyInstaller onefile build (3-10 min)")
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


def step5(version):
    step(f"Step 5/{TOTAL_STEPS} - Build Windows installer (Inno Setup)")
    iscc = find_iscc()
    if iscc is None:
        print("    [SKIP] 没找到 ISCC.exe，只产出免安装 exe。")
        print("           装好 Inno Setup 6 后重跑即可得到安装包：")
        print("           https://jrsoftware.org/isdl.php")
        return None
    print(f"    Compiler: {iscc}")
    rc = run([iscc, str(ISS_FILE), f"/DMyAppVersion={version}"], timeout=900)
    if rc != 0:
        fail("Inno Setup failed. 检查 installer_windows.iss 与 dist/PDFeverything.exe")
    built = sorted(DIST_DIR.glob(f"PDFeverything_Setup_v{version}.exe"))
    if not built:
        fail(f"Installer not found in {DIST_DIR}")
    installer = built[0]
    size_mb = installer.stat().st_size / 1024 / 1024
    print(f"    File size: {size_mb:.1f} MB")
    # 交付物放项目根目录，dist/ 只当作中间产物目录
    root_copy = PROJECT_DIR / installer.name
    shutil.copy2(installer, root_copy)
    ok(f"Installer ready: {root_copy}")
    return root_copy


def finish(installer):
    print()
    print("=" * 60)
    print("           Build Successful!")
    print("=" * 60)
    print()
    print(f"  免安装版: {OUTPUT_EXE.name}  "
          f"({OUTPUT_EXE.stat().st_size / 1024 / 1024:.1f} MB)")
    if installer:
        print(f"  安装包:   {installer.name}  "
              f"({installer.stat().st_size / 1024 / 1024:.1f} MB)")
        print()
        print("  分发安装包即可：双击 → 选择语言 → 装到本机 → 开始菜单/桌面快捷方式。")
    else:
        print()
        print("  本次没有生成安装包（缺 Inno Setup 6）。")
    print()
    print("=" * 60)
    try:
        os.startfile(str(DIST_DIR))
    except Exception:
        pass
    pause("\nPress Enter to exit...")


def main():
    print_banner()
    version = read_version()
    print(f"    Version: {version}")
    step1()
    step2()
    step3()
    step4()
    installer = step5(version) if not EXE_ONLY else None
    finish(installer)


if __name__ == "__main__":
    main()
