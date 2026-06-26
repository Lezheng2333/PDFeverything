<h1 align="center">
  <img src="resources/app_icon.ico" width="64" align="center" />
  &nbsp;PDFeverything
</h1>

<p align="center">
  <b>🪄 The PDF Swiss Army Knife</b><br>
  <sub>Throw in PDFs, Word docs, PowerPoints, Excel sheets, images, text files —<br>get one clean PDF out the other end. No fuss.</sub>
</p>

<p align="center">
  <a href="https://github.com/Lezheng2333/PDFeverything/releases"><img src="https://img.shields.io/badge/platform-macOS%20%7C%20Windows-blue?style=flat-square" /></a>
  <a href="https://github.com/Lezheng2333/PDFeverything/releases"><img src="https://img.shields.io/github/v/release/Lezheng2333/PDFeverything?style=flat-square" /></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-green?style=flat-square" /></a>
</p>

---

## ✨ Why PDFeverything?

You've been there: a Word report here, a PDF scan there, some photos of the whiteboard, an Excel chart… and now someone wants "*one combined PDF please, by 5pm*". 😤

**PDFeverything is built for exactly this moment.**

Drag everything in — any combination of PDFs, Word documents, PowerPoint decks, Excel spreadsheets, PNGs, JPEGs, text files — and it merges them into **one unified PDF**, in the order you decide, with progress you can watch.

| Platform | Download |
|---|---|
| 🍎 macOS (Apple Silicon) | [`PDFeverything_macOS.zip`](https://github.com/Lezheng2333/PDFeverything/releases/latest) |
| 🪟 Windows 10/11 (64-bit) | [`PDFeverything.exe`](https://github.com/Lezheng2333/PDFeverything/releases/latest) |

> 🔗 [**Latest Release →**](https://github.com/Lezheng2333/PDFeverything/releases/latest)

## 🆕 What's New in v1.1.0

- 🌐 **English UI** — toggle between Chinese and English in Settings > Language
- 🪟 **Windows Office COM** — native Word/PPT/Excel conversion on Windows (no fallback renderer needed!)
- 🤖 **AI Agent CLI mode** — `PDFeverything.exe merge -i a.pdf b.pdf -o out.pdf` from any terminal

---

## 🎯 The Killer Feature: Mixed-File Merge

```
📄 report.docx   (2 pages)
📊 chart.xlsx    (1 page)
🖼️ photo.jpg    (1 page)
📄 appendix.pdf  (5 pages)

         🪄  one click  🪄
              ↓
    ┌─────────────────────┐
    │   unified.pdf       │
    │   9 pages, in order │
    └─────────────────────┘
```

Every file goes through its own converter (AppleScript → Office on macOS, or pure-Python fallback), then everything gets stitched together. If one file fails, the rest still go through — you get a summary of what worked and what didn't.

## 🔧 Everything It Can Do

| Operation | What it does |
|---|---|
| 🔀 **Mixed Merge** | PDF + Word + PPT + Excel + images + text → one PDF |
| 🔗 **PDF Merge** | Combine multiple PDFs in any order |
| ✂️ **PDF Split** | Split by page, by chunks of N pages, or by custom ranges |
| 🖼️ **Images → PDF** | Turn a batch of images into a single PDF |
| 📝 **Word → PDF** | Convert `.docx` / `.doc` files to PDF |
| 📊 **PPT / Excel → PDF** | Convert `.pptx` and `.xlsx` files |
| 📄 **PDF → Images** | Export each PDF page as a PNG |
| 📤 **Extract Text** | Pull out all text from a PDF |
| 🖼️ **Extract Images** | Rip embedded images from a PDF |
| 🗜️ **Compress** | Shrink PDF file size (lossless / medium / aggressive) |
| 💧 **Watermark** | Stamp a text or PDF overlay on every page |
| 🔒 **Encrypt** | Set an open-password on a PDF |
| 🔓 **Decrypt** | Remove password protection |
| 🔄 **Rotate** | Rotate pages 90° / 180° / 270° |
| ℹ️ **Info** | Inspect page count, metadata, encryption status |

## 📥 Supported Inputs

| Category | Extensions |
|---|---|
| 📄 PDF | `.pdf` |
| 🖼️ Images | `.png` `.jpg` `.jpeg` `.gif` `.bmp` `.tiff` `.webp` |
| 📝 Word | `.docx` `.doc` `.rtf` |
| 📊 PowerPoint | `.pptx` `.ppt` |
| 📈 Excel | `.xlsx` `.xls` `.csv` |
| 📃 Text & Code | `.txt` `.md` `.json` `.xml` `.html` `.py` `.yml` … |

## 🖥️ The GUI

```
┌──────────────────────────────────────────────┐
│  📄 doc.pdf        [🔼] [🔽] [✖]            │
│  📊 data.xlsx      [🔼] [🔽] [✖]            │
│  🖼️ photo.jpg      [🔼] [🔽] [✖]            │
│  📝 report.docx    [🔼] [🔽] [✖]            │
│                                              │
│  ── drag & drop files here ──               │
│                                              │
│  [🔀 Merge All →]       [✂️ Split...]        │
│  [🗜️ Compress...]       [💧 Watermark...]    │
│  [🔒 Encrypt...]        [🔄 Rotate...]       │
│                                              │
│  ████████████░░░░░░  78%                     │
│  Converting: report.docx (3/5)...            │
└──────────────────────────────────────────────┘
```

- 🖱️ **Drag & drop** files from Finder / Explorer
- 🔄 **Reorder** with arrow buttons or by dragging inside the list
- ⚡ **Multi-threaded** — never freezes, always shows progress
- 🧠 **Smart buttons** — the UI adapts to what's in your file list
- 🌐 **Bilingual UI** — switch between Chinese and English (Settings > Language)

## 🤖 CLI Mode (for AI Agents)

The compiled executable works as a **headless CLI tool** — no Python, no GUI, no dependencies:

```bash
# AI agents can call these commands directly:
PDFeverything.exe merge -i a.pdf b.pdf -o merged.pdf
PDFeverything.exe info -i document.pdf
PDFeverything.exe compress -i big.pdf -o small.pdf
PDFeverything.exe -h          # full help
PDFeverything.exe --version   # 1.1.0
```

Any AI agent (Claude, ChatGPT, local automation scripts) can drive PDFeverything without installing anything — just the one `.exe` or `.app` file.

## 🚀 Quick Start (for Developers)

```bash
# 1. Install dependencies
pip install PyQt6 PyMuPDF pypdf pikepdf pillow python-docx python-pptx openpyxl

# 2. Launch GUI
python main.py

# 3. Or use the CLI
python pdf_tool.py merge -i a.pdf b.pdf -o merged.pdf
python pdf_tool.py info -i document.pdf
```

### Build from Source

**Windows** (one-file portable exe):
```bash
pyinstaller build_windows.spec --noconfirm --clean
# → dist/PDFeverything.exe
```

**macOS** (app bundle):
```bash
pyinstaller PDFeverything.spec --noconfirm --clean
# → dist/PDFeverything.app
```

## 🧱 Tech Stack

| Layer | Tech |
|---|---|
| 🖼️ GUI | **PyQt6** — native look on both macOS & Windows |
| 🧠 PDF Engine | **PyMuPDF** + **pypdf** + **pikepdf** |
| 📝 Office Converters | **AppleScript** (macOS, high-fidelity) / **python-docx** + **python-pptx** + **openpyxl** (fallback) |
| 📦 Packaging | **PyInstaller** (onefile on Windows, app bundle on macOS) |

## 📄 License

MIT — do whatever you want with it. [LICENSE](resources/LICENSE.txt)
