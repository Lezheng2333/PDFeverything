# PDFeverything

**One-stop PDF processing tool with GUI** — merge, split, convert, compress, watermark, and more.

| Platform | Download |
|---|---|
| 🍎 macOS | `PDFeverything.app` (Apple Silicon) |
| 🪟 Windows | `PDFeverything.exe` (64-bit, portable) |

## Features

- **Merge PDFs** — order files, one-click merge
- **Split PDFs** — by page, by range, or custom
- **Mixed files → PDF** 🎯 — select PDF + Word + images + text, merge into one unified PDF
- **Format conversion** — Word (.docx), PowerPoint (.pptx), Excel (.xlsx), images, text → PDF
- **Compress** — reduce PDF file size
- **Watermark** — text or PDF overlay
- **Encrypt / Decrypt** — password protect or remove password
- **Rotate** — pages by 90/180/270 degrees
- **Extract** — text or embedded images from PDF
- **PDF → Images** — each page as PNG
- **Images → PDF** — combine image files into one PDF

## Supported Input Formats

| Category | Extensions |
|---|---|
| PDF | `.pdf` |
| Images | `.png` `.jpg` `.jpeg` `.gif` `.bmp` `.tiff` `.webp` |
| Word | `.docx` `.doc` `.rtf` |
| PowerPoint | `.pptx` `.ppt` |
| Excel | `.xlsx` `.xls` `.csv` |
| Text | `.txt` `.md` `.json` `.xml` `.html` `.py` ... |

## Download

Go to [Releases](../../releases) and download the latest version:

- **macOS**: `PDFeverything_macOS.zip` → unzip → double-click `PDFeverything.app`
- **Windows**: `PDFeverything.exe` → double-click (portable, no install needed)

> macOS users: first launch, right-click → Open (to bypass Gatekeeper).

## Build from Source

```bash
pip install PyQt6 PyMuPDF pypdf pikepdf pillow python-docx python-pptx openpyxl
python main.py
```

### Windows Build

```bash
# onefile mode — outputs a single PDFeverything.exe
pyinstaller build_windows.spec --noconfirm --clean
```

### macOS Build

```bash
# generates PDFeverything.app bundle
pyinstaller PDFeverything.spec --noconfirm --clean
```

## Tech Stack

Python • PyQt6 • PyMuPDF • pypdf • pikepdf • python-docx

## License

MIT
