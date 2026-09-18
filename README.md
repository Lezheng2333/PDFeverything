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
  <a href="https://github.com/Lezheng2333/PDFeverything/releases/latest"><img src="https://img.shields.io/badge/version-v1.5.0-007aff?style=flat-square" /></a>
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
| 🪟 Windows 10/11 (64-bit) | [`PDFeverything.exe`](https://github.com/Lezheng2333/PDFeverything/releases/latest) |

> 🔗 [**Latest Release →**](https://github.com/Lezheng2333/PDFeverything/releases/latest)

## 🆕 What's New in v1.5.0

**Correctness and speed — a full hardening pass over every layer.**

- 🚀 **Opens any PDF instantly** — a 1000-page document used to render *every* page
  at 100% before the first pixel appeared (≈2 GB RAM, seconds of CPU). Now only the
  visible window is rendered, with a bounded look-ahead ring: **120 pages open in
  27 ms using 8 MB of cache** (was 240 MB).
- 🔍 **`PDF → Word` no longer loses text** — PyMuPDF's block tuples were unpacked in
  the wrong order, so every block after the first was rasterised as an image or
  dropped. A 5-block page produced 1 paragraph; it now produces all 5.
- 📊 **`PDF → Excel` really extracts tables** — table extraction called a PyMuPDF
  attribute that no longer exists, so table pages silently vanished from the output.
- 🀄 **Chinese/Japanese/Korean text is preserved** — text files, Word/PPT/Excel
  fallbacks and watermarks rendered through Latin-1-only fonts, turning CJK into
  `·······`. A CJK font is now selected automatically.
- 🔐 **Working encryption** — `cryptography` is now a declared dependency
  (AES-256 instead of legacy RC4-128), an empty password is rejected instead of
  silently producing an unprotected file, and `info` reports encryption status for
  locked files instead of failing.
- 🗜️ **Compression modes that do something** — `lossless` / `medium` / `max` now
  resample and re-encode images instead of all behaving identically.
- 💧 **Watermarks obey their settings** — opacity is written to the PDF graphics
  state, the angle is applied as a real rotation (45° used to collapse to 0°), and
  CJK watermark text renders properly.
- 🧵 **Cancel actually cancels** — the old `cancel()` blocked the UI thread for 5 s
  and the 60-minute timeout re-emitted its error on every progress tick. Now the
  worker cancels cooperatively, never blocks the GUI, and reports exactly once.
- 🧩 **Batches survive bad files** — one corrupt input used to abort the whole run;
  failures are now collected per file and reported with the success count.
- 🔗 **MCP stream is clean** — PyMuPDF's one-time stdout notice desynchronised the
  JSON-RPC channel, and a blank line killed the server. Both fixed, plus `ping`
  support and correct notification handling.
- 🖱️ **Grid selection is instant** — box-select no longer re-renders every
  thumbnail on every mouse-move (0.87 ms → 0.01 ms per event on a 30-page doc).
- 🪟 **Window resize re-centres pages** — the layout is recomputed on resize and
  when the reader tab becomes visible, instead of keeping stale geometry.
- 🗂️ **Real undo for CLI/MCP page editing** — `page-undo` / `page-redo` /
  `page-history` used to be stateless no-ops; the history is now persisted per file.
- ✨ **CLI polish** — new `mixed-merge` command, `--mode` for compression,
  DPI validation, tolerant page-range parsing (`1-5`, `1–5`, `1,3,5`, `all`,
  full-width commas) and clear errors instead of silent no-ops.
- 🧪 **Test suites added** — `tests/test_core.py` (51 checks) and
  `tests/test_gui.py` (45 checks) plus the reader QA suite (38 checks).

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

PDFeverything comes with a built-in **Model Context Protocol (MCP)** server. Any AI agent (Claude Desktop, Claude Code, Cursor, etc.) can discover all 23 PDF tools and call them directly — **no Python, no install, just the app file**.

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

### What the AI sees (23 tools)

Once connected, the agent automatically discovers these tools — no manual instruction needed:

| Tool | Description |
|---|---|
| `pdf_merge` | Merge several PDFs into one, in the order you list them |
| `pdf_split` | Split a PDF into single pages (or by custom ranges) |
| `pdf_info` | Metadata: page count, size, author, title, encryption status |
| `pdf_extract_text` | Extract all text from a PDF to a .txt file |
| `pdf_extract_images` | Extract every embedded image to a folder |
| `pdf_to_images` | Render each page to a PNG (adjustable DPI) |
| `images_to_pdf` | Combine images (PNG/JPG/GIF/…) into one PDF |
| `pdf_to_word` | Convert a PDF to Word (.docx), keeping text and tables |
| `pdf_to_ppt` | Convert a PDF to PowerPoint (.pptx), one slide per page |
| `pdf_to_excel` | Extract PDF tables into Excel sheets (.xlsx) |
| `pdf_compress` | Shrink a PDF (lossless / medium / max) |
| `pdf_watermark` | Add a text watermark with real opacity and angle |
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

### 🆕 v1.5.0 新功能

**一次覆盖全链路的正确性与性能加固。**

- 🚀 **任意大小的 PDF 秒开** — 以前打开 1000 页文档会先把**每一页**渲染到 100%
  （约 2GB 内存、数秒 CPU）才显示第一个像素。现在只渲染可见窗口并保留有限的
  前后缓冲：**120 页 27ms 打开、缓存 8MB**（原来 240MB）。
- 🔍 **PDF → Word 不再丢内容** — PyMuPDF 的 block 元组字段顺序被读错，导致
  第一段之后的文字块要么被当成图片，要么被直接丢弃。现在 5 段全部保留。
- 📊 **PDF → Excel 真的能提取表格** — 旧代码调用了一个在新版 PyMuPDF 中已不
  存在的属性，表格页会整个从输出里消失。
- 🀄 **中文内容不再变圆点** — 文本文件、Word/PPT/Excel 回退渲染和水印过去都
  使用只支持 Latin-1 的内置字体，中文会被替换成 `·······`；现在自动切换 CJK 字体。
- 🔐 **加密真正生效** — 声明 `cryptography` 依赖（AES-256 取代旧式 RC4-128）、
  拒绝空密码（旧版会"加密"出一个无需密码就能打开的文件）、`info` 也能正确
  报告受保护文件的加密状态。
- 🗜️ **压缩档位有实际差别** — 无损 / 中等 / 最大 现在会真正重采样并重新编码图片。
- 💧 **水印参数全部生效** — 透明度写入 PDF 图形状态、角度按真实旋转应用
  （45° 过去会被归零）、中文水印正常渲染。
- 🧵 **取消就是取消** — 旧的 `cancel()` 会阻塞界面 5 秒，60 分钟超时还会在每个
  进度回调里重复弹错。现在协作式取消、不阻塞界面、只报告一次。
- 🧩 **批量不再被单个坏文件中断** — 失败的输入会被逐个收集，并给出成功/失败汇总。
- 🔗 **MCP 输出流干净** — PyMuPDF 的一次性 stdout 提示会打乱 JSON-RPC 通道，
  空行还会直接结束服务；均已修复，并补上 `ping` 与通知处理。
- 🖱️ **网格框选变快** — 拖拽框选不再每次鼠标移动都重绘全部缩略图
  （30 页文档：0.87ms → 0.01ms / 事件）。
- 🪟 **窗口缩放后页面重新居中** — 缩放窗口或阅读 Tab 首次显示时会重算布局。
- 🗂️ **CLI/MCP 页面编辑有真正的撤销** — `page-undo` / `page-redo` /
  `page-history` 过去是无状态空操作，现在按文件持久化历史。
- ✨ **CLI 打磨** — 新增 `mixed-merge` 命令、压缩 `--mode`、DPI 校验、
  容错的页码范围解析（`1-5`、`1–5`、`1,3,5`、`all`、全角逗号）以及明确的报错。
- 🧪 **新增测试套件** — `tests/test_core.py`（51 项）、`tests/test_gui.py`（45 项）
  以及阅读器 QA 套件（38 项）。

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

PDFeverything 内置了 **Model Context Protocol (MCP)** 服务器。任何 AI Agent（Claude Desktop、Claude Code、Cursor 等）都能自动发现全部 23 个 PDF 工具并直接调用——**无需安装 Python、无需额外依赖，只要有这个 app 文件就行**。

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

#### AI 能看到的 23 个工具

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

**Windows**（单文件便携版）:
```bash
pip install pywin32   # Windows Office COM 支持
pyinstaller build_windows.spec --noconfirm --clean
# → dist/PDFeverything.exe
```

**macOS**（App Bundle）:
```bash
pyinstaller PDFeverything.spec --noconfirm --clean
# → dist/PDFeverything.app
```

### 🧱 技术栈

| 层 | 技术 |
|---|---|
| 🖼️ 界面 | **PyQt6** — macOS / Windows 原生体验 |
| 🧠 PDF 引擎 | **PyMuPDF** + **pypdf** + **pikepdf** |
| 📝 Office 转换 | **AppleScript** (macOS) / **COM** (Windows) / **python-docx** + **python-pptx** + **openpyxl** (备选) |
| 🔌 AI 集成 | **MCP (Model Context Protocol)** — 23 个工具自动发现 |
| 📦 打包 | **PyInstaller** (Windows onefile / macOS app bundle) |

### 📄 许可证

MIT — 随便用。 [LICENSE](resources/LICENSE.txt)
