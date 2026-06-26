# PDFeverything — Windows Build Guide

## Prerequisites

- **Windows 10/11 64-bit**
- **Python 3.10+** ([python.org](https://www.python.org/downloads/), check "Add Python to PATH")
- **Internet** (to download dependencies)

## One-Click Build

1. Copy the entire `PDFeverything` folder to your Windows PC
2. Double-click `build_windows.bat`
3. Wait 5-15 minutes
4. `dist\PDFeverything.exe` opens automatically

## What You Get

A single `dist\PDFeverything.exe` file (~80-120 MB).

**No install required.** Copy this one file to any Windows PC. Double-click to run.

## Build Steps (automatic)

```
[1/4] Check Python
[2/4] Install dependencies (PyQt6, PyMuPDF, etc.)
[3/4] Clean old build
[4/4] PyInstaller onefile packaging (slowest step)
```

## Troubleshooting

| Problem | Fix |
|---|---|
| bat window flashes and disappears | Open CMD in the folder, run `python build_windows.py` to see errors |
| pip install fails | Check network, or use mirror: `pip install xxx -i https://pypi.tuna.tsinghua.edu.cn/simple` |
| Antivirus blocks PyInstaller | Add project folder to Defender exclusion list |
| Out of disk space | PyInstaller needs ~2 GB temp space |

## Output

| File | Description |
|---|---|
| `dist\PDFeverything.exe` | **Final product — copy-and-run, no install** |
