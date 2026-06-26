================================================================
  PDFEVERYTHING — 开发日志
================================================================

Ver 0.1.0 | 2026-06-26
----------------------------------------------------------------

  Ver 0.1.0 | CLI 原型
    - 创建 Python CLI 工具 pdf_tool.py，12 个 PDF 操作
    - merge / split / extract-text / extract-images / to-images
      / from-images / compress / watermark / encrypt / decrypt / rotate / info
    - 依赖 PyMuPDF + pypdf + pikepdf + Pillow + pdfplumber
    - argparse 子命令分发

  Ver 0.2.0 | Core 层重构
    - core/pdf_ops.py：PdfOperator 静态方法类，progress_callback 支持
    - core/utils.py：文件分类、编码检测、临时文件管理
    - core/converters.py：ConverterRegistry 注册表模式
      —— ImageConverter / TextConverter / WordConverter /
         PowerPointConverter / ExcelConverter / PdfPassThroughConverter
    - core/merger.py：混合文件合并流水线（逐文件转换→合并）
    - macOS Word/PPT/Excel 通过 AppleScript 调用 Office 原生转换
    - python-docx + PyMuPDF 纯 Python 渲染回退方案
    - pdf_tool.py 重构为调用 core/pdf_ops.py

  Ver 0.3.0 | PyQt6 GUI 框架
    - gui/main_window.py：双 Tab 主窗口（合并与转换 / PDF 工具）
    - gui/file_list_widget.py：拖拽文件列表 + 工具栏 + 右键菜单
    - gui/workers.py：QThread BaseWorker，后台多线程不阻塞 UI
    - gui/dialogs.py：加密/解密/水印/旋转/压缩/拆分/信息对话框
    - main.py：CLI 模式 / GUI 模式自动切换
    - macOS .app 封装（PyInstaller + .icns 图标）
    - Windows .exe 封装（PyInstaller onefile + NSIS 安装程序→onefile 单文件）

----------------------------------------------------------------

Ver 1.0.0 | 2026-06-26 — 首个正式发布
----------------------------------------------------------------

  Ver 1.0.0 | 首次 Release
    - GitHub Release v1.0.0，macOS .app + Windows .exe 双平台发布
    - 应用图标：PDF 文字 + 花体 SignPainter "everything"
    - README 双语完整文档（英文 + 中文）
    - 混合文件 → 统一 PDF 作为核心功能突出展示
    - macOS Dock 图标 + Windows 任务栏图标

  Ver 1.0.1 | Word 转换修复
    - BUGFIX: AppleScript Word 转换失败（"变量 theDoc 没有定义"）
      — open 命令不返回引用，改用 open→active document
    - BUGFIX: _applescript_convert 弱校验——增加 PDF 页数验证
    - BUGFIX: python-docx 回退渲染器忽略嵌入式图片——增加
      docx inline_shape 提取 + page.insert_image 嵌入

----------------------------------------------------------------

Ver 1.1.0 | 2026-06-26 — i18n + Windows Office COM + CLI 模式
----------------------------------------------------------------

  Ver 1.1.0 | 国际化 + Windows Office + AI CLI
    - 新增 gui/i18n.py 翻译系统：zh / en 170+ 键位
    - Settings → Language 菜单切换中英文，所有 UI 即时刷新
    - 所有 GUI 文件重构为 tr() 调用（main_window / dialogs /
      file_list_widget）
    - Windows Office COM 集成：win32com 调用 Word/PPT/Excel 原生转换
      (pywin32)，macOS 保持 AppleScript
    - 跨平台 Office 检测：core/utils.py 平台感知
    - CLI 模式增强：-h / --help / --version / --mcp 标志
    - AI Agent 无头调用支持：PDFeverything.exe merge -i a.pdf -o out.pdf
    - main.py HELP_TEXT 完整命令参考

  Ver 1.1.1 | 图标优化 + README 双语
    - 应用图标重绘：everything 字体从 SignPainter 72px→96px，间距 +50px
    - README 新版本文档独立 badge（v1.1.0 蓝色版）
    - 中文 README 完整同步：GUI 预览、CLI 用法、技术栈
    - README 标题图标从 .ico 改为 .png（GitHub 不渲染 .ico）

  Ver 1.1.2 | MCP 服务器
    - 新增 mcp/server.py：Model Context Protocol JSON-RPC 服务器
    - 13 个工具 + 完整 JSON Schema（参数类型/必填/描述）
    - main.py --mcp 标志从编译后 exe/app 启动 MCP
    - Claude Desktop / Claude Code / Cursor 配置文档
    - BUGFIX: NSIS 中文路径报错——复制到临时英文目录打包

----------------------------------------------------------------

Ver 1.2.0 | 2026-06-26 — PDF 反向转换 + GUI 简化 + 批量处理
----------------------------------------------------------------

  Ver 1.2.0 | PDF→Word / PDF→PPT / PDF→Excel
    - core/pdf_ops.py 新增 to_word / to_ppt / to_excel
      - to_word：PyMuPDF 提取文字+表格→python-docx 重建 .docx
      - to_ppt：每页渲染为全幅图片→python-pptx 幻灯片
      - to_excel：Page.find_tables() 提取→openpyxl 每个表一个工作表
    - pdf_tool.py 新增 to-word / to-ppt / to-excel 子命令
    - main.py CLI_COMMANDS + HELP_TEXT 新增 3 个命令
    - mcp/server.py 新增 pdf_to_word / pdf_to_ppt / pdf_to_excel 工具
      （16 tools total）
    - GUI 工具 Tab 新增 3 个按钮 + 处理函数
    - i18n 新增 3 个翻译键
    - README EN+CN 功能表 + MCP 工具列表 + 计数更新（13→16）
    - 版本号 1.1.0→1.2.0（main.py / spec / README / mcp/server.py）

  Ver 1.2.1 | 批量处理 + UI 简化 + 鲁棒性加固
    - UI 简化：合并面板删除 Images→PDF 和 Word→PDF 按钮，
      只保留一个"合并为统一 PDF"按钮，自动识别文件类型
    - 批量处理：所有操作（压缩/水印/加密/解密/旋转/提取/
      转Word/转PPT/转Excel）均支持多文件批量
      — 1 个文件→文件对话框，多个→输出目录自动命名
    - gui/main_window.py 新增 _run_batch() 通用批处理辅助方法
    - gui/main_window.py 新增 _pick_input_files() 多文件拾取器
      （优先从文件列表，回退多选文件对话框）
    - 批处理进度条显示文件名和进度（Compress (3/12): report.pdf）
    - 批处理结果汇总弹窗列出所有输出文件
    - 文件列表保护：最大 200 文件，单文件上限 500MB，跳过 0 字节文件
    - 批量确认：文件数 >20 弹确认框，上限 200 超过截断
    - BaseWorker 加固：60min 硬超时，MemoryError 捕获，进度值钳位 0-100
    - 取消按钮：5 秒宽限期→force terminate
    - BUGFIX: Dock 运行图标恢复——main.py 中 app.setWindowIcon()
      从 bundle 读 app_icon.png 正确设置

  Ver 1.2.2 | Skill 本地化
    - 创建 .claude/RELEASE_CHECKLIST.md：6 步预发布检查清单
    - 覆盖新功能接线（7 个文件）、工具计数一致性、版本字符串、
      图标格式、CLI/MCP/GUI 测试、重编译与发布
    - 创建 CLAUDE.md + DEVELOPMENT_LOG.md 开发文档

----------------------------------------------------------------

Ver 1.3.0 | 2026-06-26 — PDF 阅读器
----------------------------------------------------------------

  Ver 1.3.0 | PDF 阅读器（初版）
    - 新增 gui/pdf_reader_widget.py：清爽单页 PDF 阅读器
      —— fitz Pixmap → QImage → QPixmap 渲染管线
    - 顶部工具栏 + 单页翻页模式
    - 缩放：适应宽度 / 适应页面 / 100-300% / Ctrl+滚轮
    - MainWindow 第 3 个 Tab "📖 Reader"，File → Open PDF (Ctrl+P)
    - 双击文件列表 PDF → 自动切换到阅读器

  Ver 1.3.1 | 阅读器重设计 — 底栏 + 3 种阅读模式 + 触控板
    - 工具栏移至窗口底部，最大化阅读区域
    - 3 种阅读模式：
      · Scroll（默认）：连续垂直滚动，所有页面堆叠，触控板平滑滚动
      · Single：逐页翻看，◀▶ 按钮 / ←→ 键盘 / 页码跳转
      · Grid：2 列缩略图网格，点击缩略图切换到 Single 模式
    - 触控板双指捏合缩放（macOS+Windows 原生手势，无需 Ctrl）
    - QScrollArea 原生触控板惯性滚动
    - 底栏新增 Scroll / Single / Grid 三按钮切换模式
    - i18n 新增 reader_scroll / reader_single / reader_grid 翻译键

  Ver 1.3.2 | 阅读器性能重写 — 标签池 + 全量预渲染 + 缩放弹窗
    - 标签池复用：所有页面 QLabel 只创建一次（_build_labels），
      模式切换只移动/隐藏，不销毁重建（6ms 切换）
    - 空间换时间：打开 PDF 时预渲染所有页面到缓存（MAX_CACHE=2000），
      后续滚动/翻页/缩放变更瞬间完成
    - 关闭 PDF 时清空所有缓存+标签，内存释放
    - 触控板双指捏合缩放无需 Ctrl（phase 检测 + 角度/像素比值法），
      缩放时弹出居中半透明百分比弹窗（1.2 秒自动消失）
    - Fit Width / Fit Page 改为 checkable 按钮，已激活时不再触发重渲染
    - 按钮悬停 3 秒后光标旁弹出功能解释（tooltip）
    - 阅读器工具栏按钮中英文本地化
    - 滚动时自动追踪当前页码（scroll→page sync）
    - 测试通过：Hello Algo 379p/18MB，打开 4.5s，模式切换 6ms，
      滚动流畅 60fps
    - BUGFIX: setFixedSize 容器无显示 — label.setParent + absolute move 解决
    - BUGFIX: QWheelEvent 缩放不支持 macOS 原生手势 — phase + angleDelta 双检测
    - BUGFIX: Grid 模式切换耗时 2.7s — 标签池复用消除重建开销
