<h1 align="center">
  <img src="resources/app_icon_readme.png" width="64" align="center" />
  &nbsp;PDFeverything
</h1>

<p align="center">
  <b>🪄 The PDF Swiss Army Knife</b><br>
  <sub>Throw in PDFs, Word docs, PowerPoints, Excel sheets, images, text files —<br>get one clean PDF out the other end. No fuss.<br>Built-in <b>high-performance PDF reader</b> with vector-grade rendering.</sub>
</p>

<p align="center">
  <a href="https://github.com/Lezheng2333/PDFeverything/releases"><img src="https://img.shields.io/badge/platform-macOS%20%7C%20Windows-blue?style=flat-square" /></a>
  <a href="https://github.com/Lezheng2333/PDFeverything/releases/latest"><img src="https://img.shields.io/badge/version-v1.9.0-007aff?style=flat-square" /></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-green?style=flat-square" /></a>
</p>

<p align="center">
  <sub><a href="#chinese">🇨🇳 中文版 ↓</a></sub>
</p>

---

## ✨ Why PDFeverything?

You've been there: a Word report here, a PDF scan there, some photos of the whiteboard, an Excel chart… and now someone wants "*one combined PDF please, by 5pm*". 😤

**PDFeverything is built for exactly this moment.**

Drag everything in — any combination of PDFs, Word documents, PowerPoint decks, Excel spreadsheets, PNGs, JPEGs, text files — and it merges them into **one unified PDF**, in the order you decide, with progress you can watch.

| Platform | Download |
|---|---|
| 🍎 macOS (Apple Silicon) | [`PDFeverything_macOS.zip`](https://github.com/Lezheng2333/PDFeverything/releases/latest) |
| 🪟 Windows 10/11 (64-bit) | [`PDFeverything_Setup_v1.9.0.exe`](https://github.com/Lezheng2333/PDFeverything/releases/latest) |

> 🔗 [**Latest Release →**](https://github.com/Lezheng2333/PDFeverything/releases/latest)
>
> 🪟 The Windows download is an **installer** — bilingual wizard, licence page, Start Menu
> entry, optional desktop shortcut and a standard uninstaller. No Python required.

## 🆕 What's New in v1.9.0

**A QA-led hardening round: 19 defects fixed, hot paths made several times faster.**

Every item below came out of an adversarial test pass (malformed input, boundary
values, hostile page ranges, cross-channel consistency, memory accounting) plus an
independent audit of the reader. Each fix has a regression test that failed before it.

- 🧠 **The reader's memory ceiling is real now.** The 400 MB pixmap cache stopped
  evicting the moment it met a 100%-zoom page — the exact entries a freshly opened
  document is full of — so it grew without limit (measured **638 MB** against a 400 MB
  cap). Eviction is now two-tier: disposable zoomed renders first, then off-screen
  bases, never the page you are looking at. It also charged the device pixel ratio
  twice, over-counting 4× on Retina and making the cap behave like 100 MB.
- 🖱️ **Grid clicks hit the page you clicked.** Grid cells were hit-tested with
  *label-local* mouse coordinates against a *container-space* grid, so **every**
  thumbnail resolved to page 1 — "click page 5, press Delete" deleted page 1. The left
  edge of any thumbnail produced the phantom index `-1`, which could duplicate the last
  page during a drag-sort.
- 🛡️ **Drag-sort no longer aborts the app.** Reordering rebuilt the document and left
  the reader holding a closed handle; the next line raised inside a Qt slot, which
  terminates the process and lost unsaved edits with no prompt.
- ⚡ **Zoom and resize are ~10× faster on long documents.** Layout read
  `doc[i].rect` for every page on every scroll-stop, zoom tick and resize — 7.5 ms of a
  9.5 ms pass at 1000 pages, i.e. most of a 16.7 ms frame budget per pinch tick. Page
  geometry is now cached: **9.5 ms → 0.94 ms** per layout, **11.9 ms → 1.55 ms** per
  pinch tick. A 1000-page PDF still opens in **30 ms** using **10 MB**.
- 🪶 **Edits stay lazy.** Deleting a page re-rendered the entire document at 100% on the
  GUI thread (189 MB for 100 pages, ~1.9 GB at 1000). Only the visible rows are
  materialised now — the windowed renderer finally holds for edits too.
- ↩️ **Undo history actually works from the CLI.** The journal was keyed on
  `(path, size, mtime)`, so a command's own output never matched its input and
  `page-undo` always answered "nothing to undo". Commands now edit in place when `-o`
  is omitted, and the journal identity is recorded so it survives the rewrite.
  Journal snapshots are also byte-budgeted and stale ones are swept — it used to keep
  50 full copies of the document in RAM *and* on disk forever.
- 🔐 **Password-protected PDFs explain themselves.** Every operation used to leak a
  library internal ("File has not been decrypted", "document closed or encrypted",
  "PasswordError"). All 16 entry points now return one actionable message.
- 🧩 **One page-range grammar for all three channels.** The MCP server had its own
  splitter that rejected what the CLI accepted (`1–5`, `1，3`, `3-1`, `1..5`) and
  crashed on others. GUI, CLI and MCP now share `core.utils.parse_page_ranges`, and
  truncated specs like `1-` are refused instead of silently meaning `1`.
- 📐 **Text→PDF wrapping measures instead of guessing.** A fixed 6.5 pt/char estimate
  left Latin text 85 pt short of the margin and pushed CJK **54 pt past the page edge**.
  Chunks are now measured with the real font.
- 🧹 **CLI stops lying.** An unknown command silently opened the GUI with exit code 0
  (a failed scripted call looked successful); it now prints a suggestion and exits 2.
- 🎯 **Per-document state resets on open.** Search hits, highlights and edit mode used
  to survive a file switch: a 100-page document's results stayed in the sidebar over a
  3-page one, the page label could read "61 / 3", and old hit rectangles were baked into
  the new document's pages.
- 🖼️ **Fit-mode renders follow a resize.** The fit cache key ignored the viewport, so
  after resizing, the label kept the pre-resize pixmap (424×600 inside a 809×1145 frame)
  and never filled the window again.
- 🧪 **A hostile-file pass.** 0-page, 0-byte, truncated, fake-header and
  password-protected files are now opened and edited without a crash; a failed open
  reports what went wrong instead of leaving a blank dead-end.
- 🧰 Plus: reading position is saved on ⌘Q (not only on ✕), a force-terminated worker
  releases the UI, the tooltip uses one timer instead of one per hover, JPG export
  honours the filename you chose, and a stray `print()` that corrupted the MCP
  JSON-RPC stream is gone.
- 🧪 **New test gates**: `tests/qa_adversarial.py` (170 probes: robustness, accuracy,
  cross-channel consistency, performance and temp-file hygiene) and
  `tests/qa_reader_defects.py` (37 reader regressions, one per defect above).
  Full set: **93 core + 70 GUI + 38 reader + 85 reader-comprehensive + 37 reader-defects
  + 170 adversarial = 493 checks**.

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

## 📖 Built-in PDF Reader

A high-performance PDF reader with **vector-grade rendering** — rivaling Acrobat and WPS.

| Feature | Detail |
|---|---|
| 🎨 **Vector-grade quality** | Exact zoom×dpr rendering, MuPDF native 8-bit sub-pixel anti-aliasing |
| 🖥️ **Full HiDPI/Retina** | 1:1 native pixel mapping, crisp text at any zoom level |
| 📜 **Scroll & Grid modes** | Continuous vertical scroll or 3-column thumbnail grid |
| ⚡ **Two-pass zoom** | Pass 1 (<5ms) instant pixel scale + Pass 2 (40ms) sharp re-render |
| 🤏 **Trackpad pinch** | Native pinch-to-zoom with phase detection |
| 💾 **LRU cache** | 400MB memory limit, immortal 100% base, zoom-level cache reuse |
| 🔍 **Smart navigation** | Bisect page tracking, async visible-range refresh on scroll stop |

## 🔧 Everything It Can Do

| Operation | What it does |
|---|---|
| 📖 **PDF Reader** | Scroll & Grid modes, vector-grade rendering, trackpad pinch-to-zoom |
| 🔀 **Mixed Merge** | PDF + Word + PPT + Excel + images + text → one PDF |
| 🔗 **PDF Merge** | Combine multiple PDFs in any order |
| ✂️ **PDF Split** | Split by page, by chunks of N pages, or by custom ranges |
| 🖼️ **Images → PDF** | Turn a batch of images into a single PDF |
| 📝 **Word → PDF** | Convert `.docx` / `.doc` files to PDF |
| 📊 **PPT / Excel → PDF** | Convert `.pptx` and `.xlsx` files |
| 📝 **PDF → Word** | Convert PDF to editable `.docx` |
| 📊 **PDF → PowerPoint** | Convert PDF pages to `.pptx` slides |
| 📈 **PDF → Excel** | Extract PDF tables to `.xlsx` |
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

## 🤖 AI Agent Integration (MCP Server)

PDFeverything comes with a built-in **Model Context Protocol (MCP)** server. Any AI agent (Claude Desktop, Claude Code, Cursor, etc.) can discover all 29 PDF tools and call them directly — **no Python, no install, just the app file**.

### How it works

The same `.exe` / `.app` binary supports three modes:

| Mode | macOS | Windows |
|---|---|---|
| 🖥️ **GUI** | double-click `.app` | double-click `.exe` |
| ⌨️ **CLI** | ``/path/to/PDFeverything.app/Contents/MacOS/PDFeverything merge -i a.pdf -o out.pdf`` | `PDFeverything.exe merge -i a.pdf b.pdf -o out.pdf` |
| 🔌 **MCP** | ``/path/to/PDFeverything.app/Contents/MacOS/PDFeverything --mcp`` | `PDFeverything.exe --mcp` |

### Setup — Claude Desktop

Add to `~/.claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "pdfeverything": {
      "command": "/Applications/PDFeverything.app/Contents/MacOS/PDFeverything",
      "args": ["--mcp"]
    }
  }
}
```

**Windows:**
```json
{
  "mcpServers": {
    "pdfeverything": {
      "command": "C:\\Program Files\\PDFeverything\\PDFeverything.exe",
      "args": ["--mcp"]
    }
  }
}
```

### Setup — Claude Code

Add to `.claude/settings.json` in your project:

```json
{
  "mcpServers": {
    "pdfeverything": {
      "type": "stdio",
      "command": "/Applications/PDFeverything.app/Contents/MacOS/PDFeverything",
      "args": ["--mcp"]
    }
  }
}
```

### What the AI sees (29 tools)

Once connected, the agent automatically discovers these tools — no manual instruction needed:

| Tool | Description |
|---|---|
| `pdf_merge` | Merge several PDFs into one, in the order you list them |
| `pdf_split` | Split a PDF into single pages (or by custom ranges) |
| `pdf_info` | Metadata: page count, size, author, title, encryption status |
| `pdf_outline` | Bookmark / table-of-contents tree with target pages |
| `pdf_search` | Find text in a PDF — every match with page, position and context |
| `pdf_extract_text` | Extract all text from a PDF to a .txt file |
| `pdf_extract_images` | Extract every embedded image to a folder |
| `pdf_to_images` | Render each page to a PNG (adjustable DPI) |
| `images_to_pdf` | Combine images (PNG/JPG/GIF/…) into one PDF |
| `pdf_to_word` | Convert a PDF to Word (.docx), keeping text and tables |
| `pdf_to_ppt` | Convert a PDF to PowerPoint (.pptx), one slide per page |
| `pdf_to_excel` | Extract PDF tables into Excel sheets (.xlsx) |
| `pdf_compress` | Shrink a PDF (lossless / medium / max) |
| `pdf_watermark` | Add a text watermark with real opacity and angle |
| `pdf_insert_pages` | Insert or append pages from another PDF |
| `pdf_nup` | Impose 2/4/6/8/9/16 pages per sheet for printing |
| `pdf_set_metadata` | Edit document properties (title, author, subject, keywords) |
| `pdf_add_page_numbers` | Stamp page numbers / headers / footers with a `{n}`/`{total}` template |
| `pdf_encrypt` | Set an open password (AES-256) |
| `pdf_decrypt` | Remove the password from a PDF |
| `pdf_rotate` | Rotate pages 90/180/270° |
| `pdf_mixed_merge` | 🔥 The killer feature: merge mixed file types into one PDF |
| `pdf_delete_pages` | Delete pages by 1-based number or range |
| `pdf_rotate_pages` | Rotate specific pages |
| `pdf_move_pages` | Reorder pages by moving them before a target position |
| `pdf_extract_pages` | Extract pages into a new standalone PDF |
| `pdf_undo` | Undo the last page edit (history persists per file) |
| `pdf_redo` | Redo the last undone page edit |
| `pdf_history` | Show the recorded editing history for a file |

### Direct CLI mode (no MCP needed)

AI agents can also call the binary directly:

```bash
# macOS
/Applications/PDFeverything.app/Contents/MacOS/PDFeverything merge -i a.pdf b.pdf -o out.pdf
/Applications/PDFeverything.app/Contents/MacOS/PDFeverything info -i doc.pdf
/Applications/PDFeverything.app/Contents/MacOS/PDFeverything -h

# Windows
PDFeverything.exe merge -i a.pdf b.pdf -o out.pdf
PDFeverything.exe info -i doc.pdf
PDFeverything.exe -h
```

> 💡 **The `.app` and `.exe` are the SAME single binary.** Give it CLI args → headless mode. Give it `--mcp` → MCP server. No args → GUI. One file, three personalities.

## 🚀 Quick Start (for Developers)

```bash
# 1. Install dependencies
pip install PyQt6 PyMuPDF pypdf pikepdf pillow python-docx python-pptx openpyxl

# 2. Launch GUI
python main.py

# 3. Or use the CLI
python pdf_tool.py merge -i a.pdf b.pdf -o merged.pdf
python pdf_tool.py info -i document.pdf

# 4. Or start the MCP server
python mcp/server.py
```

### Build from Source

**Windows** (installer + portable exe, needs [Inno Setup 6](https://jrsoftware.org/isdl.php)):
```bash
python build_windows.py
# → PDFeverything_Setup_v1.9.0.exe   installer (copied to the project root)
# → dist/PDFeverything.exe           portable payload, no install
```

**macOS** (app bundle):
```bash
pyinstaller PDFeverything.spec --noconfirm --clean
# → dist/PDFeverything.app
```

## 🧪 Testing

Three gates run on every release, plus two adversarial suites added in v1.9.0:

```bash
.venv/bin/python tests/test_core.py                            # core / CLI / MCP / i18n   93
QT_QPA_PLATFORM=offscreen .venv/bin/python tests/test_gui.py    # workers / batch / dialogs 70
QT_QPA_PLATFORM=offscreen .venv/bin/python tests/qa_reader.py   # reader QA                 38
QT_QPA_PLATFORM=offscreen .venv/bin/python tests/test_reader.py # reader comprehensive      85

# adversarial suites — these attack the software, they do not just re-check it
.venv/bin/python tests/qa_adversarial.py                        # robustness / accuracy   170
QT_QPA_PLATFORM=offscreen .venv/bin/python tests/qa_reader_defects.py  # reader defects    37
```

`tests/qa_adversarial.py` covers malformed and hostile input (0-byte, truncated,
fake-header, encrypted, 0-page PDFs), page-range boundary values, cross-channel
consistency between GUI/CLI/MCP, pixel-level accuracy oracles, memory and
file-descriptor ceilings, and temp-file hygiene. Every probe prints the concrete
evidence when it fails.

`tests/qa_reader_defects.py` holds one regression per reader defect fixed in v1.9.0;
each of them failed before its fix.

**Total: 493 checks.**

## 🧱 Tech Stack

| Layer | Tech |
|---|---|
| 🖼️ GUI | **PyQt6** — native look on both macOS & Windows |
| 🧠 PDF Engine | **PyMuPDF** + **pypdf** + **pikepdf** |
| 📝 Office Converters | **AppleScript** (macOS) / **COM** (Windows) / **python-docx** + **python-pptx** + **openpyxl** (fallback) |
| 📦 Packaging | **PyInstaller** (onefile on Windows, app bundle on macOS) |

## 📄 License

MIT — do whatever you want with it. [LICENSE](resources/LICENSE.txt)

---

<a id="chinese"></a>
<h2 align="center">🇨🇳 中文介绍</h2>

<p align="center">
  <b>🪄 PDF 万能工具箱</b><br>
  <sub>把 PDF、Word、PPT、Excel、图片、文本文件统统丢进来 ——<br>一键合成一个整整齐齐的 PDF。就这么简单。<br>内置<b>高性能 PDF 阅读器</b>，矢量级渲染画质。</sub>
</p>

### 🎯 核心功能：混合文件合并

```
📄 报告.docx     (2 页)
📊 图表.xlsx     (1 页)
🖼️ 照片.jpg     (1 页)
📄 附录.pdf      (5 页)

         🪄  一键合并  🪄
              ↓
    ┌─────────────────────┐
    │   统一输出.pdf       │
    │   9 页，顺序不变     │
    └─────────────────────┘
```

把不同类型的文件拖进来，每个文件经过专用转换器处理，然后按顺序合并。某个文件转换失败了也不影响其他的——最后会给你一份汇总报告。

### 📖 内置 PDF 阅读器

高性能 PDF 阅读器，**矢量级渲染画质**——媲美 Acrobat 和 WPS。

| 特性 | 详情 |
|---|---|
| 🎨 **矢量级画质** | 精确 zoom×dpr 渲染，MuPDF 原生 8 位子像素抗锯齿 |
| 🖥️ **全 HiDPI/Retina** | 1:1 原生物理像素映射，任意缩放级别文字锐利 |
| 📜 **连续 / 网格双模式** | 连续垂直滚动或 3 列缩略图网格 |
| ⚡ **两阶段缩放** | Pass 1 (<5ms) 瞬时像素拉伸 + Pass 2 (40ms) 高清重绘 |
| 🤏 **触控板捏合** | 原生手势检测，跟手缩放 |
| 💾 **LRU 缓存** | 400MB 内存上限，100% 基础永生，缩放级别缓存复用 |
| 🔍 **智能导航** | 二分页码追踪，滚动停止时异步刷新可见区域 |

### 🔧 全部功能

| 操作 | 说明 |
|---|---|
| 📖 **PDF 阅读器** | 连续/网格双模式，矢量级渲染画质，触控板捏合缩放 |
| 🔀 **混合合并** | PDF + Word + PPT + Excel + 图片 + 文本 → 一个 PDF |
| 🔗 **PDF 合并** | 多个 PDF 按任意顺序合并 |
| ✂️ **PDF 拆分** | 按页码、每 N 页或自定义范围拆分 |
| 🖼️ **图片 → PDF** | 多张图片一键合成为 PDF |
| 📝 **Word → PDF** | 转换 .docx / .doc 文件 |
| 📊 **PPT / Excel → PDF** | 转换 .pptx / .xlsx 文件 |
| 📝 **PDF → Word** | 将 PDF 转换为可编辑的 .docx |
| 📊 **PDF → PowerPoint** | PDF 每页转为 .pptx 幻灯片 |
| 📈 **PDF → Excel** | 提取 PDF 表格为 .xlsx |
| 📄 **PDF → 图片** | 每页导出为 PNG |
| 📤 **提取文字** | 提取 PDF 中所有文字 |
| 🖼️ **提取图片** | 提取 PDF 中嵌入的图片 |
| 🗜️ **压缩** | 缩小 PDF 文件体积 |
| 💧 **水印** | 添加文字或 PDF 叠加水印 |
| 🔒 **加密 / 解密** | 设置或移除 PDF 打开密码 |
| 🔄 **旋转** | 旋转页面 90° / 180° / 270° |
| ℹ️ **信息** | 查看页数、元数据、加密状态 |

### 🆕 v1.9.0 新功能

**以 QA 为主导的加固迭代：修复 19 个缺陷，热点路径提速近 10 倍。**

下面每一条都来自对抗性测试（畸形输入、边界值、恶意页码范围、三通道一致性、
内存计量）以及一次独立的阅读器审计。每个修复都配有"修复前必然失败"的回归测试。

- 🧠 **阅读器的内存上限真正生效了** — 原先淘汰循环一遇到 100% 缩放的页面就 `break`，
  而刚打开的文档里全是这种页面，于是缓存无上限增长（实测 **638 MB** 对 400 MB 上限）。
  现在分两级淘汰：先丢可再生的缩放/缩略图渲染，再丢屏幕外的 base，绝不丢你正在看的那一页。
  同时修正了重复计算 devicePixelRatio 的问题（Retina 上 4 倍高估，使 400 MB 实际只有 100 MB）。
- 🖱️ **网格视图点哪页选哪页** — 网格单元用**标签局部坐标**去做**容器坐标**的命中测试，
  导致每个缩略图都解析成第 1 页：点第 5 页再按删除，删掉的是第 1 页。缩略图左边缘还会产生
  幽灵索引 `-1`，拖拽排序时可能复制最后一页。
- 🛡️ **拖拽排序不再让程序崩溃** — 重排会重建文档，阅读器却仍持有已关闭的句柄，
  下一行在 Qt 槽函数里抛异常 → 进程直接 abort，未保存的修改无提示丢失。
- ⚡ **长文档缩放/缩放窗口快约 10 倍** — 布局在每次滚动停止、缩放、改变窗口时都要为
  每一页读 `doc[i].rect`（1000 页时占 9.5ms 中的 7.5ms，等于一次捏合缩放吃掉大半个帧预算）。
  页码几何现已缓存：**布局 9.5ms → 0.94ms**，**捏合一次 11.9ms → 1.55ms**。
  1000 页 PDF 打开仍是 **30ms**、占用 **10MB**。
- 🪶 **编辑后依然惰性渲染** — 删除一页曾在 GUI 线程上把整本文档按 100% 全部重渲
  （100 页 189MB，1000 页约 1.9GB）。现在只渲染可见行。
- ↩️ **CLI 的撤销历史真的能用了** — 日志键基于 `(路径, 大小, mtime)`，
  导致命令自己的输出永远匹配不上输入，`page-undo` 总是回答"没有可撤销的操作"。
  现在省略 `-o` 即就地修改，且日志身份被持久记录，改写后依然能找回历史。
  日志快照同时按字节预算裁剪，陈旧日志会被清理（原先会在内存和磁盘各留 50 份完整副本）。
- 🔐 **加密 PDF 给出可操作的提示** — 原先 16 个入口各自泄漏底层库的内部错误
  （"File has not been decrypted"、"document closed or encrypted"、"PasswordError"）。
- 🧩 **三通道统一页码语法** — MCP 曾有一套自己的解析器，CLI 能识别的 `1–5`、`1，3`、
  `3-1`、`1..5` 它会报错，另一些则直接崩溃。现在 GUI/CLI/MCP 共用
  `core.utils.parse_page_ranges`，且 `1-` 这类残缺写法会被明确拒绝而不是悄悄当成 `1`。
- 📐 **文本转 PDF 按实际宽度折行** — 原先按 6.5pt/字符估算：拉丁文比右边距短 85pt，
  中文则**超出页面 54pt**。现在用真实字体测量。
- 🧹 **CLI 不再"假装成功"** — 未知命令原先会静默打开 GUI 并返回 0（脚本调用失败看起来像成功），
  现在会给出相近命令建议并以退出码 2 结束。
- 🎯 **切换文件时重置每文档状态** — 搜索结果、高亮、编辑模式原先会跨文件残留：
  100 页文档的结果留在 3 页文档的侧栏里，页码可能显示 "61 / 3"，
  旧文档的命中矩形还会被画进新文档的位图。
- 🖼️ **适应窗口模式跟随窗口尺寸** — fit 缓存键没有包含视口尺寸，改变窗口后
  标签仍拿着改变前的位图（424×600 塞在 809×1145 的框里），永远不会铺满。
- 🧪 **恶意文件专项测试** — 0 页、0 字节、截断、伪造文件头、加密 PDF 现在都能
  正常打开/编辑而不崩溃；打开失败会说明原因而不是留下一片空白。
- 🧰 其他：⌘Q 退出也会记住阅读位置（原先只有点 ✕ 才记）、强制终止的 worker 会释放界面、
  工具提示改为单个复用定时器、JPG 导出遵循你选的文件名、
  以及一处会污染 MCP JSON-RPC 流的 `print()` 已移除。
- 🧪 **新增测试门禁**：`tests/qa_adversarial.py`（170 项：鲁棒性/准确性/三通道一致性/
  性能/临时文件卫生）与 `tests/qa_reader_defects.py`（37 项阅读器回归，每个缺陷一项）。
  全套件：**93 核心 + 70 GUI + 38 阅读器 + 85 阅读器综合 + 37 阅读器缺陷 + 170 对抗 = 493 项**。

### 🖥️ 界面预览

```
┌──────────────────────────────────────────────┐
│  📄 doc.pdf        [🔼] [🔽] [✖]            │
│  📊 data.xlsx      [🔼] [🔽] [✖]            │
│  🖼️ photo.jpg      [🔼] [🔽] [✖]            │
│  📝 report.docx    [🔼] [🔽] [✖]            │
│                                              │
│  ── 拖放文件到此处 ──                        │
│                                              │
│  [🔀 合并为统一 PDF]   [✂️ 拆分...]          │
│  [🗜️ 压缩...]        [💧 水印...]          │
│  [🔒 加密...]        [🔄 旋转...]           │
│                                              │
│  ████████████░░░░░░  78%                     │
│  转换中: 报告.docx (3/5)...                  │
└──────────────────────────────────────────────┘
```

- 🖱️ 从资源管理器/Finder **拖放**文件
- 🔄 用按钮或拖动**调整顺序**
- ⚡ **多线程**处理 — 界面永不卡顿，实时进度条
- 🧠 **智能按钮** — 根据文件列表内容自动变化

### 🤖 AI Agent 集成（MCP 服务器）

PDFeverything 内置了 **Model Context Protocol (MCP)** 服务器。任何 AI Agent（Claude Desktop、Claude Code、Cursor 等）都能自动发现全部 29 个 PDF 工具并直接调用——**无需安装 Python、无需额外依赖，只要有这个 app 文件就行**。

#### 同一个文件，三种模式

| 模式 | macOS | Windows |
|---|---|---|
| 🖥️ **GUI** | 双击 `.app` | 双击 `.exe` |
| ⌨️ **命令行** | ``/Applications/PDFeverything.app/Contents/MacOS/PDFeverything merge -i a.pdf -o out.pdf`` | `PDFeverything.exe merge -i a.pdf b.pdf -o out.pdf` |
| 🔌 **MCP** | ``/Applications/PDFeverything.app/Contents/MacOS/PDFeverything --mcp`` | `PDFeverything.exe --mcp` |

#### 配置 Claude Desktop

在 `~/.claude/claude_desktop_config.json` 中添加：

```json
{
  "mcpServers": {
    "pdfeverything": {
      "command": "/Applications/PDFeverything.app/Contents/MacOS/PDFeverything",
      "args": ["--mcp"]
    }
  }
}
```

**Windows：**
```json
{
  "mcpServers": {
    "pdfeverything": {
      "command": "C:\\Program Files\\PDFeverything\\PDFeverything.exe",
      "args": ["--mcp"]
    }
  }
}
```

#### 配置 Claude Code

在项目下的 `.claude/settings.json` 中添加：

```json
{
  "mcpServers": {
    "pdfeverything": {
      "type": "stdio",
      "command": "/Applications/PDFeverything.app/Contents/MacOS/PDFeverything",
      "args": ["--mcp"]
    }
  }
}
```

#### AI 能看到的 29 个工具

连接后 Agent 会自动发现这些工具——无需手动教它：

| 工具 | 说明 |
|---|---|
| `pdf_merge` | Merge multiple PDFs into one |
| `pdf_split` | Split PDF by pages or custom ranges |
| `pdf_info` | Metadata: pages, size, author, encryption status |
| `pdf_extract_text` | Extract all text from a PDF |
| `pdf_extract_images` | Extract embedded images |
| `pdf_to_images` | Convert PDF pages to PNG |
| `images_to_pdf` | Images → single PDF |
| `pdf_to_word` | PDF → Word (.docx) |
| `pdf_to_ppt` | PDF → PowerPoint (.pptx) |
| `pdf_to_excel` | PDF tables → Excel (.xlsx) |
| `pdf_compress` | Reduce file size (lossless / medium / max) |
| `pdf_watermark` | Add a text watermark (opacity + angle honoured) |
| `pdf_encrypt` | Set an open password |
| `pdf_decrypt` | Remove the password |
| `pdf_rotate` | Rotate pages 90/180/270° |
| `pdf_mixed_merge` | 🔥 Mixed files → unified PDF |
| `pdf_delete_pages` | Delete pages by number |
| `pdf_rotate_pages` | Rotate specific pages |
| `pdf_move_pages` | Reorder pages |
| `pdf_extract_pages` | Extract pages into a new PDF |
| `pdf_undo` | Undo the last page edit (persistent history) |
| `pdf_redo` | Redo the last undone edit |
| `pdf_history` | Show the editing history of a file |

#### 直接 CLI 调用（无需 MCP）

AI Agent 也可以直接调用二进制：

```bash
# macOS
/Applications/PDFeverything.app/Contents/MacOS/PDFeverything merge -i a.pdf b.pdf -o out.pdf
/Applications/PDFeverything.app/Contents/MacOS/PDFeverything info -i doc.pdf
/Applications/PDFeverything.app/Contents/MacOS/PDFeverything -h

# Windows
PDFeverything.exe merge -i a.pdf b.pdf -o out.pdf
PDFeverything.exe info -i doc.pdf
PDFeverything.exe -h
```

> 💡 **`.app` 和 `.exe` 就是同一个二进制文件。** 给参数 → 命令行模式。给 `--mcp` → MCP 服务器。不给参数 → GUI。一个文件，三种用法。

### 🚀 开发者快速开始

```bash
pip install PyQt6 PyMuPDF pypdf pikepdf pillow python-docx python-pptx openpyxl
python main.py            # 启动 GUI
python pdf_tool.py info -i document.pdf   # CLI 模式
```

### 📦 从源码构建

**Windows**（安装包 + 便携版 exe，需要 [Inno Setup 6](https://jrsoftware.org/isdl.php)）:
```bash
python build_windows.py
# → PDFeverything_Setup_v1.9.0.exe   安装包（同时复制到项目根目录）
# → dist/PDFeverything.exe           便携版载荷，免安装
```

**macOS**（App Bundle）:
```bash
pyinstaller PDFeverything.spec --noconfirm --clean
# → dist/PDFeverything.app
```

### 🧪 测试

发布前跑三个门禁套件，v1.9.0 起再加两个对抗性套件：

```bash
.venv/bin/python tests/test_core.py                            # 核心 / CLI / MCP / i18n   93
QT_QPA_PLATFORM=offscreen .venv/bin/python tests/test_gui.py    # Worker / 批量 / 对话框   70
QT_QPA_PLATFORM=offscreen .venv/bin/python tests/qa_reader.py   # 阅读器 QA                38
QT_QPA_PLATFORM=offscreen .venv/bin/python tests/test_reader.py # 阅读器综合测试            85

# 对抗性套件 —— 它们主动攻击软件，而不只是复检既有行为
.venv/bin/python tests/qa_adversarial.py                        # 鲁棒性 / 准确性         170
QT_QPA_PLATFORM=offscreen .venv/bin/python tests/qa_reader_defects.py  # 阅读器缺陷回归    37
```

`tests/qa_adversarial.py` 覆盖畸形与恶意输入（0 字节、截断、伪造文件头、加密、0 页 PDF）、
页码范围边界值、GUI/CLI/MCP 三通道一致性、像素级准确性判据、
内存与文件描述符上限、临时文件卫生。每一条失败时都会打印具体证据。

`tests/qa_reader_defects.py` 中每个 v1.9.0 修复的阅读器缺陷都对应一项回归，
它们在修复前必然失败。

**合计 493 项。**

### 🧱 技术栈

| 层 | 技术 |
|---|---|
| 🖼️ 界面 | **PyQt6** — macOS / Windows 原生体验 |
| 🧠 PDF 引擎 | **PyMuPDF** + **pypdf** + **pikepdf** |
| 📝 Office 转换 | **AppleScript** (macOS) / **COM** (Windows) / **python-docx** + **python-pptx** + **openpyxl** (备选) |
| 🔌 AI 集成 | **MCP (Model Context Protocol)** — 29 个工具自动发现 |
| 📦 打包 | **PyInstaller** (Windows onefile / macOS app bundle) |

### 📄 许可证

MIT — 随便用。 [LICENSE](resources/LICENSE.txt)
