# PDFeverything 2.0.2 验收记录 — macOS 兼容性

日期：2026-11-09
范围：issue #1「不能在 macOS 26 上运行」的根因修复与可移植构建

## 1. 问题复现（2.0.1 构建）

```text
$ .venv/bin/python -m core.compat PDFeverything.app --max-macos 13.0
Architecture: arm64
Declared    : LSMinimumSystemVersion=11.0
Effective   : macOS 27.0+  (Contents/Frameworks/libssl.3.dylib)
Mach-O files: 140
FAIL  69 file(s) require a newer macOS than 13.0
FAIL  LSMinimumSystemVersion says 11.0 but binaries need 27.0 (app cannot launch on the
      systems it claims to support)
RESULT: FAILED
```

关键文件：

| 文件 | minos | 来源 |
|---|---|---|
| `libssl.3.dylib` / `libcrypto.3.dylib` / `libreadline.8.dylib` | 27.0 | Homebrew（构建机） |
| `libpython3.14.dylib` + stdlib 扩展 | 26.0 | pyenv 本地编译 |
| `pikepdf/_core*.so` | 14.0 | PyPI wheel |
| Qt 6.11 框架 | 13.0 | PyQt6 wheel |

`import hashlib` → `_hashlib` → `libcrypto.3.dylib`（27.0）即触发 dyld 拒绝加载，
所以 macOS 26 上双击直接闪退。

## 2. 修复后的构建

```text
$ python build_macos.py --min-macos 13.0
Preflight
  Python 3.14.0 (arm64), deployment target macOS 10.15
  PyQt6: Qt needs macOS 13.0+
  PyInstaller 6.21.0
  cryptography: needs macOS 11.0+
  PIL: needs macOS 11.0+
...
Audit
Bundle      : dist/PDFeverything.app
Architecture: arm64
Declared    : LSMinimumSystemVersion=13.0
Effective   : macOS 13.0+
Mach-O files: 145
Signature   : adhoc (valid)
RESULT: OK
```

产物：

| 项 | 值 |
|---|---|
| `PDFeverything_macOS_v2.0.2.zip` | 72,561,457 bytes（2.0.1：73,156,388） |
| SHA-256 | `e9a33231521ff7560f9b3acf3f3a63a1abc28e428d46393134dc75d1efa8ae90` |
| 架构 | arm64（Apple 芯片原生） |
| 实际最低系统 | macOS 13.0 |
| 外部路径引用 | 0（OpenSSL 3 / zstd 已随包，不再外链 Homebrew） |
| 签名 | ad-hoc（本机验证通过；正式分发需 Developer ID + 公证） |

构建环境：macOS 27.0.1 arm64 / Python 3.14.0（python.org `python-3.14.0-macos11.pkg`，
framework 部署目标 10.15）/ PyQt6 6.11.0（Qt 6.11.0）/ PyInstaller 6.21.0。

## 3. 回归测试

八套门禁全绿，共 562 项：

| 套件 | 结果 |
|---|---|
| `tests/test_core.py` | 97/97 |
| `tests/test_macos_compat.py`（新增） | 40/40 |
| `tests/test_gui.py` | 70/70 |
| `tests/qa_reader.py` | 38/38 |
| `tests/test_reader.py` | 85/85 |
| `tests/qa_adversarial.py` | 170/170 |
| `tests/qa_reader_defects.py` | 37/37 |
| `tests/test_studio.py` | 25/25 |

## 4. 冻结包冒烟

在 `dist/PDFeverything.app` 上执行（不是源码树）：

```text
PDFeverything v2.0.2
PDFeverything doctor → macOS 27.0.1 (arm64), Python 3.14.0 (built for 10.15+),
                       Qt 6.11.0, Declared 13.0, Effective 13.0, arm64, adhoc valid
compress lossless  → 1,613 → 1,487 bytes, output readable (MuPDF path, no pikepdf)
encrypt / decrypt  → 往返成功
info               → 3 页，未加密
GUI                → 直接执行与 `open dist/PDFeverything.app` 均正常驻留，无 stderr
--doctor 原生模块   → ssl / hashlib / zlib / lzma / bz2 全部 ok（sqlite3 未打包，按设计跳过）
```

构建审计同时检查两类可移植性缺陷，任一命中即 `RESULT: FAILED`：

1. 任何一个 Mach-O 的 `LC_BUILD_VERSION.minos` 高于 `--min-macos`；
2. 任何一个二进制的 dylib 依赖指向系统目录之外的绝对路径（`/Library/...`、
   `/opt/homebrew/...` 等）——这正是「PyInstaller 找不到 libssl 就静默跳过、
   到用户机器上才崩」的形态；本次构建因此发现并补回 OpenSSL/zstd。

## 5. 已知边界

- **未公证**：本地没有 Developer ID 证书，当前产物为 ad-hoc 签名。从网上下载的副本
  在 macOS 15+ / 26 上仍会被 Gatekeeper 拦一次，用户需在「隐私与安全性」里放行；
  正式发布建议按 `docs/MACOS_COMPAT.md` §5 走 `--identity ... --notarize`。
- **最低系统 13.0**：由 Qt 6.11 决定（Qt 6.12 抬到 14.4）。macOS 11/12 不再支持，
  原因与取舍见 `docs/MACOS_COMPAT.md` §3。
- **Windows 产物**：本机不能交叉编译；`installer_windows.iss` 版本已同步 2.0.2，
  需通过 `build-windows-installer.yml` 出包后补传 Release 资产。
- **未在真实 macOS 26 机器上复测**：当前环境为 macOS 27.0.1。审计证明所有 145 个
  Mach-O 的 `minos` ≤ 13.0，dyld 不会因版本拒绝加载；仍建议发布前在 macOS 26 上做一次
  双击冒烟。
