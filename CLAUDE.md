# PDFEVERYTHING — Claude Code 备忘录

## 🎯 Core Philosophy (设计铁律)

每行代码、每个设计决策必须服务于五个核心指标：

| # | 指标 | 英文 | 铁律 |
|---|---|---|---|
| 1 | **清爽** | Clean | 界面零杂乱，按钮数量最小化，视觉噪音最低。阅读模式比操作模式更突出。 |
| 2 | **简约** | Minimal | 一个按钮能完成的事不用两个。合并面板只有 `[Merge→]` 一个按钮。底栏只在需要时出现。 |
| 3 | **全面** | Comprehensive | 16 种 PDF 操作、6 种格式互转、3 通道（GUI/CLI/MCP）、3 种阅读模式。不多不少，刚好够用。 |
| 4 | **速度快** | Fast | 打开 <0.2s，模式切换瞬间（缓存命中小于 5ms），渲染 2x 超采样 + SmoothTransform，滚轮缩放 60fps。 |
| 5 | **轻量化** | Lightweight | 单 exe 80MB（onefile 压缩），内存 <200MB（含 50 页缓存），不依赖外部运行时。PyMuPDF=C 内核，Qt=C++ 内核。 |

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
- **macOS 打包**：`pyinstaller PDFeverything.spec --noconfirm --clean`
- **Windows 打包**：`python build_windows.py`（在 Windows 上运行）
- **GitHub 仓库**：`Lezheng2333/PDFeverything`

## 上下文恢复

- 每次对话开始或 compact 之后，必须阅读 `DEVELOPMENT_LOG.md` 了解最新开发进展和最近版本变更
- 阅读本文件中的"关键架构决策"和"文件职责"理解代码组织方式

## 当前开发状态

### 最新版本：v1.3.17
- 📖 **PDF 阅读器**：两模式（Scroll 连续滚动 / Grid 3 列缩略图）
  - **矢量级画质**：精确分辨率渲染（无 SSAA/无 downscale），MuPDF 原生子像素 AA，8 位 AA 最大化
  - **HiDPI 原生**：`devicePixelRatio` 驱动渲染矩阵 + `setDevicePixelRatio` 1:1 像素映射
  - Immortal 100% base：全部缩放从 100% 渲染基础出发，零累积误差
  - 两阶段缩放：Pass 1 瞬时像素拉伸 (<5ms) + Pass 2 精确分辨率渲染 (40ms)
  - LRU OrderedDict 缓存，400MB 物理内存硬限制（dpr² 校正），驻留特权保护 base + fit modes
  - 双 Timer 页码追踪：throttle 30ms 粗略 + debounce 150ms bisect 精确校准
  - 懒渲染 ±1 页（3 页）；懒预渲染首 5 页 + 10ms 间隔后台排队
  - 触控板捏合缩放（40ms 高清响应）、拖放打开、欢迎页、✕ 关闭
  - 默认 100% 缩放打开，缩放/Fit 模式切换后保持滚动位置
- GUI 中英文双语切换（Settings → Language）
- 16 个 PDF 操作（CLI + GUI + MCP 三通道）
- macOS + Windows 双平台 onedir/onefile 发布
- 液态玻璃艺术风格 1024px 应用图标

### 开发路线
```
✅ CLI原型 ✅ Core重构 ✅ PyQt6 GUI ✅ macOS/Windows发布
✅ i18n双语 ✅ Windows COM ✅ MCP服务器 ✅ PDF反向转换
✅ 批量处理 ✅ 鲁棒性加固 ✅ PDF阅读器 ✅ LRU缓存
✅ Immortal 100% base ✅ 矢量级画质(精确解析度+MuPDF原生AA) => 持续优化
```

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
│   ├── utils.py             # 文件分类、编码检测、临时文件、跨平台 Office 检测
│   ├── pdf_ops.py           # PdfOperator — 16 个 PDF 处理方法（所有通道共享）
│   ├── converters.py        # ConverterRegistry — 6 种格式→PDF 转换器
│   └── merger.py            # merge_mixed_files() — 混合文件→统一 PDF 流水线
├── gui/
│   ├── __init__.py
│   ├── main_window.py       # MainWindow — 双 Tab + 进度条 + 语言切换
│   ├── file_list_widget.py  # FileListWidget — 拖拽列表 + 工具栏 + 保护层
│   ├── workers.py           # BaseWorker(QThread) — 60min 超时 + 优雅取消
│   ├── dialogs.py           # 7 个操作对话框（加密/解密/水印/旋转/压缩/拆分/信息）
│   ├── pdf_reader_widget.py  # PdfReaderWidget — PDF 阅读器（LRU 缓存 + 两阶段缩放）
│   └── i18n.py              # tr() — 170+ 键位中英文翻译表
├── mcp/
│   ├── __init__.py
│   ├── server.py            # MCP JSON-RPC stdio 服务器 — 16 tools
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
PdfOperator (static methods)
  ├── get_info / merge / split
  ├── extract_text / extract_images
  ├── to_images / from_images / compress
  ├── watermark / text_watermark
  ├── encrypt / decrypt / rotate
  └── to_word / to_ppt / to_excel

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
  └── InfoDialog — PDF 元数据显示
```

### mcp

```
TOOLS (16 entries) — JSON-RPC tools/list 响应
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
