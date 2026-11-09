# macOS 兼容性：为什么 2.0.1 在 macOS 26 上打不开，2.0.2 怎么修

> 对应 issue：<https://github.com/Lezheng2333/PDFeverything/issues/1>
>
> 一句话：**2.0.1 的包其实要求 macOS 27.0**，`Info.plist` 里写的 `11.0` 是假的；
> 2.0.2 起改为「Apple 芯片原生 arm64 + macOS 13.0 起」，并在构建时强制审计。

---

## 1. 症状

- 双击 `PDFeverything.app` 没反应，或 Dock 图标闪一下就消失；
- 终端里直接跑二进制才能看到真正的错误：

```text
dyld[...]: Library not loaded: @rpath/libcrypto.3.dylib
  Referenced from: .../PDFeverything.app/Contents/Frameworks/_hashlib...so
  Reason: tried: '...' (building for macOS 27.0, but linking in dylib built for macOS 27.0)
```

macOS 26 用户看到的是「应用已损坏」或直接闪退，因为 dyld 在 Python 启动之前就拒绝了。

## 2. 根因：每个 Mach-O 都有最低系统要求

macOS 的加载器 dyld 会读取每个二进制里的 `LC_BUILD_VERSION.minos`。只要**任何一个**
被加载的文件要求高于当前系统，整个进程就起不来。

PyInstaller 的 `.app` 会把 Python 解释器、Qt 框架、所有 C 扩展和它们链接的动态库
一起打包，因此 **包的最低系统 = 所有文件里最高的那个 minos**。

2.0.1 的实测值：

| 组件 | 来源 | minos | 说明 |
|---|---|---|---|
| `libssl.3.dylib` / `libcrypto.3.dylib` / `libreadline.8.dylib` | Homebrew（跟随构建机） | **27.0** | 直接杀死 macOS 26 |
| `libpython3.14.dylib` + 全部 stdlib 扩展 | pyenv 本地编译 | **26.0** | 继承构建机 SDK |
| `pikepdf` 的 `_core.so` | PyPI wheel | 14.0 | 官方 wheel 只发 macOS 14+ |
| Qt 6.11 框架 | PyQt6 wheel | 13.0 | Qt 官方基线 |
| PyMuPDF / cryptography / Pillow | PyPI wheel | 11.0 | 正常 |

取最大值 → **27.0**。而 `Info.plist` 写的是 `LSMinimumSystemVersion = 11.0`，
两者矛盾，构建时没有任何检查。

关键链条：`main.py` 启动 GUI 时 `import core.page_editor` → `import hashlib`
→ `_hashlib` → `libcrypto.3.dylib`（27.0）→ dyld 直接 abort。

## 3. 2.0.2 的修复

| 项目 | 2.0.1 | 2.0.2 |
|---|---|---|
| Python 运行时 | pyenv 本机编译（26.0） | **python.org 官方 universal2**（10.15/11.0） |
| OpenSSL / readline | Homebrew 动态库（27.0） | **随 Python 自带**，不再外链 Homebrew |
| pikepdf | 依赖 wheel（14.0） | **移除**，无损压缩改用 MuPDF（包更小、少一个原生依赖） |
| 架构 | 跟随构建机 | **显式 `arm64`**（Apple 芯片原生） |
| 声明最低系统 | 11.0（不实） | **13.0**（与 Qt 6.11 基线一致，可审计） |
| 构建入口 | 手敲 `pyinstaller` | `python build_macos.py`（预检 + 构建 + 签名 + 审计 + 打包） |
| 失败诊断 | 无 | `--doctor` 报告 + `~/Library/Logs/PDFeverything/crash.log` |
| 回归测试 | 无 | `tests/test_macos_compat.py`（40 项） |

最终生效最低系统 = **macOS 13.0**（Qt 6.11 是当前最稳妥、且完整支持 macOS 26/27 的
Qt 版本；Qt 6.12 会把底线抬到 14.4，所以 `requirements.txt` 钉在 `<6.12`）。

> 为什么不支持 macOS 11/12：M1 首发系统是 11，但 Apple 已停止为 13 以下提供安全更新；
> Qt 6.11 本身要求 13.0。为了 11/12 而退回 Qt 6.5 会牺牲 macOS 26/27 的兼容性，
> 对一个 PDF 工具不划算。

## 4. 构建（唯一支持的方式）

前置条件：

1. **python.org 官方 Python**（`python-3.14.0-macos11.pkg` 或更新），
   不要用 Homebrew / pyenv —— 它们会继承构建机的 deployment target；
2. `requirements.txt` 原样安装（PyQt6 已钉在 6.11.x）。

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python build_macos.py            # arm64 + macOS 13.0 + ad-hoc 签名
```

脚本会：

1. **预检**：Python 的 deployment target、Qt/PyMuPDF/cryptography/Pillow 的
   实际 minos 是否 ≤ `--min-macos`，任何一项超标立即失败并说明原因；
2. 用 `PDFeverything.spec` 构建（`target_arch=arm64`，`LSMinimumSystemVersion`
   由同一变量注入）；
3. 由内向外签名、`codesign --verify --deep --strict`；
4. **审计整个 bundle**：逐个 Mach-O 读取 minos，确认没有文件超过目标版本，
   并检查 `Info.plist` 是否撒谎；
5. 生成 `PDFeverything_macOS_vX.Y.Z.zip` + SHA-256。

手动复核：

```bash
.venv/bin/python -m core.compat dist/PDFeverything.app --max-macos 13.0
# RESULT: OK
```

## 5. 分发：Gatekeeper 与公证

ad-hoc 签名（默认）足以让 App 在本机运行，但**从网上下载的副本**会被 Gatekeeper
拦下（提示「已损坏」/「无法验证开发者」），macOS 15 起右键「打开」也不再放行。
正式分发应使用 Developer ID 并公证：

```bash
security find-identity -v -p codesigning        # 找到 "Developer ID Application: ..."
xcrun notarytool store-credentials pdfeverything \
      --apple-id you@example.com --team-id TEAMID --password <app-specific-password>

python build_macos.py \
  --identity "Developer ID Application: Your Name (TEAMID)" \
  --notarize --keychain-profile pdfeverything
```

`build_macos.py` 会用 `resources/macos_entitlements.plist`（hardened runtime +
AppleScript 自动化 + 动态库加载）签名，再 `notarytool submit --wait` + `stapler staple`。

## 6. 用户侧排障

1. 先跑诊断：

```bash
/Applications/PDFeverything.app/Contents/MacOS/PDFeverything --doctor
```

会输出 macOS 版本、Python/Qt 版本、bundle 声明与**实际**最低系统、架构、签名状态。

2. 若提示「已损坏」且确认来源可信：在 **系统设置 → 隐私与安全性** 点「仍要打开」，
   或（仅限自己确认过的文件）：

```bash
xattr -dr com.apple.quarantine /Applications/PDFeverything.app
```

3. 启动崩溃的完整 traceback 在 `~/Library/Logs/PDFeverything/crash.log`。

## 7. 版本矩阵

| 版本 | 架构 | 实际最低系统 | 状态 |
|---|---|---|---|
| 2.0.0 / 2.0.1 | arm64 | **27.0**（尽管 plist 写 11.0） | ❌ macOS 26 及以下无法启动 |
| 2.0.2 | arm64 | **13.0** | ✅ Ventura / Sonoma / Sequoia / 26 / 27 |

---

## English TL;DR

2.0.1 shipped binaries whose Mach-O deployment targets were 26.0 (pyenv-built
Python) and 27.0 (Homebrew OpenSSL/readline) while `Info.plist` claimed 11.0, so
dyld aborted the launch on macOS 26 (issue #1).

2.0.2 builds with the official python.org universal2 Python, drops `pikepdf`
(lossless compression now uses MuPDF), pins PyQt6 6.11 (Qt baseline macOS 13),
builds `arm64` explicitly, and adds `build_macos.py` + `core.compat`, which audit
every Mach-O in the bundle and fail the build if anything requires a newer macOS
than `--min-macos` (**13.0**). `PDFeverything --doctor` prints the same report
from the shipped app.
