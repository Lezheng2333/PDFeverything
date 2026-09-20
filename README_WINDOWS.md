# PDFeverything — Windows Build Guide

Builds two artifacts on Windows: the payload **`PDFeverything.exe`** (single-file,
no-install) and the **installer** `PDFeverything_Setup_v<version>.exe` that ships to users.

## Prerequisites

- **Windows 10/11 64-bit**
- **Python 3.10+** ([python.org](https://www.python.org/downloads/), check "Add Python to PATH")
- **Internet** (to download dependencies)
- **Inno Setup 6** ([jrsoftware.org/isdl.php](https://jrsoftware.org/isdl.php)) — only needed for the installer step

## One-Click Build

1. Copy the entire `PDFeverything` folder to your Windows PC
2. Double-click `build_windows.bat` (or run `python build_windows.py`)
3. Wait 5-15 minutes
4. The `dist\` folder opens when it finishes

```bash
python build_windows.py                # deps -> exe -> installer
python build_windows.py --skip-deps    # dependencies already installed (CI)
python build_windows.py --exe-only     # no-install exe only, skip the installer
```

## What You Get

| File | Purpose |
|---|---|
| `PDFeverything_Setup_v<version>.exe` | **Ship this** — the installer (copied to the project root) |
| `dist\PDFeverything_Setup_v<version>.exe` | Same installer, inside the build output dir |
| `dist\PDFeverything.exe` | Single-file no-install build; this is the installer's payload |

The installer is defined in `installer_windows.iss` (Inno Setup 6): bilingual wizard
(中文 / English), licence page, optional desktop shortcut, Start Menu entry, and a
standard uninstaller. It installs per-user by default (no UAC prompt); the first
wizard page lets the user switch to an all-users install.

## Build Steps (automatic)

```
[1/5] Check Python
[2/5] Install dependencies (PyQt6, PyMuPDF, etc.)
[3/5] Clean old build
[4/5] PyInstaller onefile packaging (slowest step)
[5/5] Inno Setup installer compile
```

If Inno Setup is missing, step 5 is skipped with a hint — the no-install exe is still
produced.

## CI Build (no Windows machine needed)

`.github/workflows/build-windows-installer.yml` runs the same pipeline on a
`windows-latest` runner and uploads the installer as a build artifact.

```bash
gh workflow run build-windows-installer.yml
gh run watch
gh run download <run-id> -n PDFeverything-Setup -D /tmp/win
```

It also runs automatically when a `v*` tag is pushed. The version number is read from
`VERSION` in `main.py` unless you pass one:

```bash
gh workflow run build-windows-installer.yml -f version=2.0.0
```

## Troubleshooting

| Problem | Fix |
|---|---|
| bat window flashes and disappears | Open CMD in the folder, run `python build_windows.py` to see errors |
| pip install fails | Check network, or use mirror: `pip install xxx -i https://pypi.tuna.tsinghua.edu.cn/simple` |
| Antivirus blocks PyInstaller | Add project folder to Defender exclusion list |
| Out of disk space | PyInstaller needs ~2 GB temp space |
| `[SKIP]` on step 5 | Inno Setup 6 not installed — see Prerequisites |

---

# PDFeverything — Windows 构建指南

在 Windows 上构建两样东西：载荷 **`PDFeverything.exe`**（单文件免安装版）和分发给
用户的**安装包** `PDFeverything_Setup_v<版本>.exe`。

## 前置条件

- **Windows 10/11 64 位**
- **Python 3.10+**（[python.org](https://www.python.org/downloads/)，安装时勾选 "Add Python to PATH"）
- **能联网**（下载依赖）
- **Inno Setup 6**（[jrsoftware.org/isdl.php](https://jrsoftware.org/isdl.php)）—— 只有生成安装包那一步需要

## 一键构建

1. 把整个 `PDFeverything` 文件夹拷到 Windows 电脑上
2. 双击 `build_windows.bat`（或执行 `python build_windows.py`）
3. 等 5–15 分钟
4. 构建结束后会自动打开 `dist\` 目录

```bash
python build_windows.py                # 依赖 → exe → 安装包
python build_windows.py --skip-deps    # 依赖已装好，跳过 pip（CI 用）
python build_windows.py --exe-only     # 只要免安装 exe，不生成安装包
```

## 产物

| 文件 | 用途 |
|---|---|
| `PDFeverything_Setup_v<版本>.exe` | **分发这个** —— 安装包（同时复制到项目根目录） |
| `dist\PDFeverything_Setup_v<版本>.exe` | 同一个安装包，位于构建输出目录内 |
| `dist\PDFeverything.exe` | 单文件免安装版；它就是安装包的载荷 |

安装包由 `installer_windows.iss` 定义（Inno Setup 6)：中英双语向导、许可协议页、
可选桌面快捷方式、开始菜单项、标准卸载程序。默认**仅为我安装**（不弹 UAC），
向导首页可切换成全机器安装。

## 构建步骤（自动）

```
[1/5] 检查 Python
[2/5] 安装依赖（PyQt6、PyMuPDF 等）
[3/5] 清理旧构建
[4/5] PyInstaller onefile 打包（最慢的一步）
[5/5] Inno Setup 编译安装包
```

没装 Inno Setup 时第 5 步会跳过并给出提示，免安装 exe 照常产出。

## CI 构建（不需要 Windows 机器）

`.github/workflows/build-windows-installer.yml` 在 `windows-latest` 跑同一条流水线，
把安装包作为构建产物上传。

```bash
gh workflow run build-windows-installer.yml
gh run watch
gh run download <run-id> -n PDFeverything-Setup -D /tmp/win
```

推 `v*` 标签时也会自动触发。版本号默认读 `main.py` 里的 `VERSION`，也可以指定：

```bash
gh workflow run build-windows-installer.yml -f version=2.0.0
```

## 常见问题

| 问题 | 解决 |
|---|---|
| bat 窗口一闪而过 | 在该目录开 CMD，执行 `python build_windows.py` 看报错 |
| pip 装不上 | 检查网络，或用镜像：`pip install xxx -i https://pypi.tuna.tsinghua.edu.cn/simple` |
| 杀毒软件拦截 PyInstaller | 把项目目录加入 Defender 排除列表 |
| 磁盘空间不足 | PyInstaller 需要约 2 GB 临时空间 |
| 第 5 步显示 `[SKIP]` | 没装 Inno Setup 6，见「前置条件」 |
