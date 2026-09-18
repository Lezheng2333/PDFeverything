# PDFEVERYTHING — Claude Code 备忘录

## 🎯 Core Philosophy (设计铁律)

每行代码、每个设计决策必须服务于五个核心指标：

| # | 指标 | 英文 | 铁律 |
|---|---|---|---|
| 1 | **清爽** | Clean | 界面零杂乱，按钮数量最小化，视觉噪音最低。阅读模式比操作模式更突出。 |
| 2 | **简约** | Minimal | 一个按钮能完成的事不用两个。合并面板只有 `[Merge→]` 一个按钮。底栏只在需要时出现。 |
| 3 | **全面** | Comprehensive | 26 种 PDF 操作、6 种格式互转、3 通道（GUI/CLI/MCP）、2 种阅读模式 + 侧栏（目录/搜索）。不多不少，刚好够用。 |
| 4 | **速度快** | Fast | 打开 <0.2s（窗口化渲染，与页数无关），模式切换瞬间（缓存命中小于 5ms），滚轮缩放 60fps，网格框选 0.01ms/事件。 |
| 5 | **轻量化** | Lightweight | 单 exe ~76MB（onefile 压缩），内存 <200MB（缓存按可见窗口增长），不依赖外部运行时。PyMuPDF=C 内核，Qt=C++ 内核。 |

> ⚡ 每次修改前自问：**我是在让软件更清爽、更简约、更全面、更快、更轻吗？** 如果答案是"不是"，换方案。

## 项目信息

- **语言**：Python 3.10+
- **GUI 框架**：PyQt6
- **主入口**：`main.py`（GUI/CLI/MCP 三模式自动切换）
- **运行命令**：
  ```bash
  python main.py                          # GUI
  python main.py merge -i a.pdf -o out.pdf # CLI
  python main.py -h                        # 帮助
  python main.py --mcp                     # MCP 服务器
  ```
- **macOS 打包**：`PYINSTALLER_CONFIG_DIR="$PWD/.buildcache" pyinstaller PDFeverything.spec --noconfirm --clean`
  （沙箱环境无法写入 `~/Library/Application Support/pyinstaller`，必须重定向缓存目录）
- **Windows 打包**：`python build_windows.py`（在 Windows 上运行）
- **GitHub 仓库**：`Lezheng2333/PDFeverything`

## 上下文恢复

- 每次对话开始或 compact 之后，必须阅读 `DEVELOPMENT_LOG.md` 了解最新开发进展和最近版本变更
- 阅读本文件中的"关键架构决策"和"文件职责"理解代码组织方式

## 当前开发状态

### 最新版本：v1.8.0
- 📖 **PDF 阅读器**：两模式（Scroll 连续滚动 / Grid 3 列缩略图）+ 可折叠侧栏（目录 / 搜索结果）
  - **窗口化渲染**：只渲染可见页 ±3 的环形窗口，1000 页文档与 3 页文档打开成本相同
  - **矢量级画质**：精确分辨率渲染（无 SSAA/无 downscale），MuPDF 原生子像素 AA
  - **HiDPI 原生**：`devicePixelRatio` 驱动渲染矩阵 + `setDevicePixelRatio` 1:1 像素映射
  - 两阶段缩放：Pass 1 瞬时像素拉伸 (<5ms) + Pass 2 精确分辨率渲染 (40ms)
  - LRU OrderedDict 缓存，400MB 内存上限（dpr² 校正），base/fit 模式驻留保护
  - 🔍 全文搜索：命中高亮绘制进位图、侧栏结果列表、⌘F 查找栏（大小写/整词/上下文）
  - 📑 目录侧栏 + 🔁 阅读位置记忆（按文件记录页码与缩放）
  - ⌨️ 快捷键：⌘F 查找 / ⌘B 侧栏 / ⌘+ ⌘− 缩放 / ⌘0 ⌘1 适应 / ⌘G 上下一个 / ←→ 翻页
  - 触控板捏合缩放、拖放打开、欢迎页、双击切换适应模式
- GUI 中英文双语切换（Settings → Language）
- 26 个 PDF 操作 + 6 种格式转换，三通道（GUI / CLI / MCP）共享同一实现，MCP 暴露 29 个工具
- macOS + Windows 双平台 onedir/onefile 发布
- 液态玻璃艺术风格 1024px 应用图标

### 开发路线
```
✅ CLI原型 ✅ Core重构 ✅ PyQt6 GUI ✅ macOS/Windows发布
✅ i18n双语 ✅ Windows COM ✅ MCP服务器 ✅ PDF反向转换
✅ 批量处理 ✅ 鲁棒性加固 ✅ PDF阅读器 ✅ LRU缓存
✅ Immortal 100% base ✅ 矢量级画质(精确解析度+MuPDF原生AA)
✅ v1.5.0 正确性大修(窗口化渲染/协作取消/CJK/加密/压缩档位) ✅ 回归测试套件
✅ v1.6.0 阅读器搜索+目录侧栏+阅读位置记忆 ✅ v1.7.0 页码/元数据/N-up/插入页面
✅ v1.8.0 界面清爽化(转换菜单/文件列表汇总) => 持续优化
```

### 测试
```bash
.venv/bin/python tests/test_core.py    # 核心 / CLI / MCP / i18n   93 项
.venv/bin/python tests/test_gui.py     # Worker / 批量 / 对话框 / 阅读器  70 项
QT_QPA_PLATFORM=offscreen .venv/bin/python tests/qa_reader.py   # 阅读器 QA  38 项
```
发布前必须三套全绿（当前 201 项）。

### 已知脆弱点补充（v1.5.0+）
- **reader 窗口化渲染**：只渲染可见页 ±3，新增页面渲染入口必须走 `_schedule_render_visible`，
  否则懒渲染环形队列不会重新布防
- **搜索高亮**：命中矩形是 PDF 坐标，绘制时按 `zoom × dpr` 换算；命中页缓存需先失效
  （`_invalidate_pages`）再重绘，否则高亮不会出现
- **page_editor 撤销**：CLI 的撤销依赖 `journal_dir()` 持久化历史，`_journal_init()`
  必须在**改动之前**调用，否则第一次编辑无法撤销；`save()` 必须带 `garbage/clean`
- **`to_word` block 元组**：PyMuPDF 返回 `(x0,y0,x1,y1,text,block_no,block_type)`，
  字段顺序写错会静默丢文字
- **MCP stdout**：任何 `print()` 都会污染 JSON-RPC 流，已全局屏蔽 PyMuPDF 提示，
  新增第三方库调用需注意

### 已知脆弱点（修改前必须理解上下文）
- **Reader 缓存键**：`z:1.000` 是 immortal base 键，`_cache_put` 中必须跳过淘汰；修改 `_zoom_key` 格式会影响所有缓存命中
- **Reader 缩放流水线**：Pass 1 必须从 100% base 出发（`base_key = (pi, "z:1.000")`），不能从 label.pixmap 出发；Pass 2 `_sharp_render` 依赖 `_pending_zoom_pct is not None` 守卫
- **_layout_labels render_missing**：缩放路径必须传 `render_missing=False`，只有 `open_pdf` 传 True；传错会导致 Pass 1 缩放结果被 100% 覆盖
- **_scroll_to_page_top()**：`_set_zoom_pct`、`_apply_fit_mode` 末尾必须调用，否则缩放后滚动位置丢失
- **i18n 接线**：新增按钮/菜单项必须在 `_retranslate_ui()` 中同步添加翻译调用，漏了会导致切语言后按钮变空白
- **MCP 工具计数**：新增/删除工具必须在 README EN+CN 的两处计数（AI 能看到的 N 个工具 / discover all N PDF tools）同步更新
- **CLI_COMMANDS 集合**：`main.py` 中的 `CLI_COMMANDS` set 决定是否跳过 GUI 启动，新增命令漏加会导致双击 exe 出黑框
- **_run_batch ext 参数**：非 PDF 输出（to-word→.docx / to-ppt→.pptx / to-excel→.xlsx / extract-text→.txt）必须传 ext 参数，否则生成错误后缀文件
- **QSettings 持久化**：`main_window.py` 中的默认输出目录、dpi、语言等设置通过 QSettings 持久化，修改设置键名会导致用户丢失偏好

## 项目结构

```
PDFeverything/
├── main.py                  # 入口：GUI / CLI / MCP 三模式路由
├── pdf_tool.py              # CLI 子命令解析 + 分发
├── core/
│   ├── __init__.py
│   ├── utils.py             # 文件分类、编码检测、临时文件、页码范围解析、Office 检测
│   ├── pdf_ops.py           # PdfOperator — 26 个 PDF 处理方法（所有通道共享）
│   ├── search.py            # 全文搜索 + 目录(书签)解析（GUI/CLI/MCP 共用）
│   ├── converters.py        # ConverterRegistry — 6 种格式→PDF 转换器（CJK 字体感知）
│   ├── page_editor.py       # 页面编辑 + 快照撤销 + 持久化历史日志
│   └── merger.py            # merge_mixed_files() — 混合文件→统一 PDF 流水线
├── gui/
│   ├── __init__.py
│   ├── main_window.py       # MainWindow — 双 Tab + 进度条 + 语言切换
│   ├── file_list_widget.py  # FileListWidget — 拖拽列表 + 工具栏 + 保护层
│   ├── workers.py           # BaseWorker(QThread) — 60min 超时 + 优雅取消
│   ├── dialogs.py           # 9 个操作对话框（加密/解密/水印/旋转/压缩/拆分/信息/页码/属性）
│   ├── pdf_reader_widget.py  # PdfReaderWidget — PDF 阅读器（LRU 缓存 + 两阶段缩放）
│   └── i18n.py              # tr() — 280+ 键位中英文翻译表（格式化异常安全）
├── mcp/
│   ├── __init__.py
│   ├── server.py            # MCP JSON-RPC stdio 服务器 — 29 tools
│   └── README.md            # Claude Desktop / Code 配置指南
├── resources/
│   ├── app_icon.icns        # macOS 图标
│   ├── app_icon.ico         # Windows 图标
│   ├── app_icon.png         # README 用 + Dock 显示
│   └── LICENSE.txt          # MIT
├── PDFeverything.spec       # PyInstaller macOS 构建配置
├── build_windows.spec       # PyInstaller Windows onefile 构建配置
├── build_windows.py         # Windows 一键构建脚本
├── build_windows.bat        # Windows 双击启动器
├── .claude/
│   └── RELEASE_CHECKLIST.md # 预发布检查清单（本地）
├── CLAUDE.md                # 本文件
├── DEVELOPMENT_LOG.md       # 开发日志
├── README.md                # 双语项目文档
└── requirements.txt         # 依赖清单
```

## 架构：三通道模型

```
          ┌─────────┐
          │  main   │
          └────┬────┘
               │
   ┌───────────┼───────────┐
   ▼           ▼           ▼
 GUI模式    CLI模式     MCP模式
   │           │           │
   │    (pdf_tool.py)  (mcp/server.py)
   │           │           │
   └───────────┴───────────┘
               │
               ▼
       core/pdf_ops.py    ← 所有通道共享同一实现
      core/converters.py
       core/merger.py
```

- **GUI**：`main.py` 无参数启动 → `launch_gui()` → PyQt6 QApplication
- **CLI**：`main.py merge -i a.pdf -o out.pdf` → 识别 `CLI_COMMANDS` → 路由到 `pdf_tool.main()`
- **MCP**：`main.py --mcp` → `launch_mcp()` → stdin/stdout JSON-RPC

## 关键架构决策

- **core 层零 GUI 依赖**：`core/` 下所有模块不导入 PyQt，CLI/GUI/MCP 共享
- **Converter 注册表模式**：新增文件格式只需实现 `BaseConverter` → `ConverterRegistry.register()`
- **progress_callback 回调注入**：所有耗时方法接受 `progress_callback(msg, pct)`，GUI 通过 worker 注入，CLI 传 None
- **QSettings 语言持久化**：`gui/i18n.py` 的 `_load_lang()` 读 QSettings，`set_language()` 写入
- **_retranslate_ui() 全局刷新**：语言切换时遍历所有 widget 调用 `tr()` 重新设文本
- **批处理决策**：1 个文件→文件对话框，多个文件→输出目录，通过 `_run_batch()` 统一处理
- **`.app` 二进制即 CLI**：`PDFeverything.app/Contents/MacOS/PDFeverything merge ...` 直接运行 CLI，同一文件三种用法

## 类结构

### core

```
PdfOperator (static methods, 22 个公开方法)
  ├── 查看/合并/拆分: get_info / merge / split
  ├── 提取: extract_text / extract_images
  ├── 图片互转: to_images / from_images
  ├── 优化与安全: compress(lossless|medium|max) / encrypt(AES-256) / decrypt
  ├── 水印: watermark(PDF 叠加) / text_watermark(文字, 支持透明度与角度)
  ├── 旋转: rotate
  ├── 排版与信息: add_page_numbers / set_metadata / nup / insert_pages
  ├── 页面增删: extract_pages / delete_pages（PyMuPDF，保留链接）
  └── 反向转换: to_word / to_ppt / to_excel

core/search.py
  ├── search_pdf() — 命中页/矩形/文字/上下文（大小写、整词、范围、上限）
  └── get_outline() — 书签树（嵌套层级 + 目标页）

BaseConverter (ABC) → ConverterRegistry
  ├── ImageConverter (.png/.jpg/.gif/...)
  ├── TextConverter (.txt/.md/.json/...)
  ├── WordConverter (.docx/.doc) — macOS AppleScript / Windows COM / python-docx 回退
  ├── PowerPointConverter (.pptx/.ppt) — AppleScript / COM / python-pptx 回退
  ├── ExcelConverter (.xlsx/.xls) — AppleScript / COM / openpyxl 回退
  └── PdfPassThroughConverter (.pdf) — 直通

merge_mixed_files() — 混合文件→统一 PDF 流水线
```

### gui

```
MainWindow(QMainWindow)
  ├── FileListWidget — 拖拽列表 + 工具栏 + 保护层
  │     ├── MAX_FILES=200, MAX_SIZE_BYTES=500MB
  │     ├── add_files / get_file_paths / retranslate_ui
  │     └── 工具栏按钮 / 右键菜单 / 外部拖入
  ├── BaseWorker(QThread) — MAX_RUNTIME_SECONDS=3600
  │     ├── progress(msg,pct) / finished(result) / error(msg)
  │     └── cancel() — 5s grace → terminate
  ├── EncryptDialog / DecryptDialog
  ├── WatermarkDialog — 文字水印 / PDF 叠加
  ├── RotateDialog — 角度选择 + 页码范围
  ├── CompressDialog — 无损 / 中等 / 最大
  ├── SplitRangeDialog — 每页 / 每N页 / 自定义
  ├── InfoDialog — PDF 元数据显示
  ├── PageNumberDialog — 页码/页眉页脚（模板 + 预览）
  └── MetadataDialog — 文档属性（仅提交改动字段）
```

### mcp

```
TOOLS (29 entries) — JSON-RPC tools/list 响应
_run_tool(name, args) → JSON result string
serve() — stdin/stdout JSON-RPC 主循环（initialize / tools/list / tools/call / shutdown）
```

## 开发日志格式规范

`DEVELOPMENT_LOG.md` 遵循以下格式规则：

1. **标题行**：`Ver X.X.X | YYYY-MM-DD — 简短概括`（不超过一行）
2. **大版本分节**：`----------------------------------------------------------------` 分隔符 + 版本号标题
3. **条目**：全部使用 `- ` 开头，2 空格缩进
4. **顺序**：新功能/优化/enhancement 在前，**BUGFIX 统一在最后**
5. **BUGFIX 格式**：`- BUGFIX: 问题描述 + 修复方法`，与其他条目同级缩进
6. 每个条目尽量控制在一行内，避免不必要的多行展开

## 发布流程

每次发布新版本时，按以下步骤操作：

1. **功能接线检查**（参照 `.claude/RELEASE_CHECKLIST.md`）：
   - 新功能是否在 7 个文件中全部注册（core > CLI > main.py > MCP > GUI > i18n > README）
   - MCP 工具计数是否与 README 一致
   - 版本字符串是否在所有位置更新
2. **开发日志**：在 `DEVELOPMENT_LOG.md` 末尾写入新版本条目
3. **测试**：
   ```bash
   python main.py -h                           # CLI 帮助
   python pdf_tool.py <new-command> -i test.pdf -o out   # 新命令
   python -c "from mcp.server import TOOLS; print(len(TOOLS))"  # MCP 工具数
   ```
4. **macOS 构建**：
   ```bash
   pyinstaller PDFeverything.spec --noconfirm --clean
   cp -R dist/PDFeverything.app . && rm -rf build
   ```
5. **GitHub Release**：
   ```bash
   zip -r /tmp/PDFeverything_macOS_vX.Y.Z.zip PDFeverything.app/
   gh release create vX.Y.Z /tmp/PDFeverything_macOS_vX.Y.Z.zip \
     --title "PDFeverything vX.Y.Z" --notes "..."
   ```
6. **Windows 构建**（在 Windows 上）：
   ```bash
   python build_windows.py
   gh release upload vX.Y.Z dist/PDFeverything.exe
   ```
