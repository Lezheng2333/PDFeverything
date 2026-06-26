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

  Ver 1.3.3 | 阅读器 v3 — 仅 Scroll+Grid，适应高度，3 列网格，关闭按钮
    - 移除单页模式，仅保留 Scroll 和 Grid 两种模式
    - 新增 Fit Height：将单页高度缩放至窗口高度
    - Fit Width/Fit Height 改为独立 checkable 按钮，互斥切换
    - Grid 改为 3 列排列，双击缩略图→Fit Height+Scroll 跳转该页
    - 连续滚动模式翻页按钮和页码常驻显示
    - 滚动时自动追踪当前页（>50% 可见区域即为当前页）
    - 翻页按钮/←→键盘：滚动到目标页，页面顶部对齐窗口顶部
    - 右下角文件名旁新增 ✕ 关闭按钮
      · 从 "File→Open" 进入→关闭后留在阅读器欢迎页
      · 从文件列表双击→关闭后自动跳转回合并 Tab
    - 预渲染改为分批异步（每批 40 页），初次加载保持 UI 响应
    - BUGFIX: Fit Width 和 Fit Page 完全相同 — 拆分为 Width/Height 两个维度
    - BUGFIX: 连续模式底栏显示翻页按钮和页码 — 改为仅 Grid 隐藏

  Ver 1.3.4 | 欢迎页 + 完整 i18n + 右键"打开方式"集成
    - 阅读器空载时显示居中欢迎页："拖入 PDF 文件以阅读" + "加载文件"按钮
    - 支持拖拽 PDF 文件到阅读器窗口直接打开
    - _retranslate_ui() 在 _init_ui() 末尾调用，所有按钮/文字启动即本地化
    - 阅读器工具栏全中文化（连续/网格/适应宽度/适应高度）
    - 所有 tooltip 中英双语
    - macOS Info.plist 注册 .pdf 文件类型（LSHandlerRank=Alternate），
      系统"打开方式"菜单中出现 PDFeverything，文件自动加入文件列表
    - main.py 新增 _collect_file_args()，忽略 -psn_ 等 macOS 噪声参数
    - 版本号升级至 1.3.0

  Ver 1.3.5 | 阅读器 v5 — 跟手缩放 + WPS 网格 + 点击编辑缩放 + 高速页码追踪
    - 缩放改为双重架构：_apply_smooth_zoom() 即时缩放现有 pixmap（跟手），
      _real_zoom_timer 250ms 防抖后执行真实渲染（清晰画质）
    - 触控板双指捏合：累积 angleDelta，每 120 单位 = 3% 缩放，50-300% 范围
    - [+] [-] 按钮 ±1% 步长，smooth=True 模式即时响应
    - 缩放比例下拉菜单（QComboBox）完全删除，替换为可点击编辑的 QLineEdit
      · QIntValidator(25-500) 限制合法输入，>500→500，<50→50，小数四舍五入
      · Enter 或失焦生效
    - 网格模式重设计（参照 WPS 网格视图）：
      · 3 列居中均匀分布，gutter 20px，缩略图按可用宽度动态计算
      · 左侧边距自动调整使网格居中
    - 页码追踪重写：_page_heights[] 数组记录每页 Y 位置，二分查找 O(log n)
      · _scroll_timer 间隔 16ms（~60fps），滚动停止立即更新页码
    - 欢迎页修复：QTimer.singleShot(100ms) 延迟显示，确保 viewport 已布局
    - BUGFIX: 欢迎页不显示 — _destroy_welcome() 清理 + center.raise_() 置顶
    - BUGFIX: 页码不更新 — 二分查找替换逐页遍历
    - BUGFIX: 网格模式双击无效 — _on_grid_dbl_click 检查 view_mode==GRID
    - BUGFIX: 缩放过慢 — smooth 即时缩放 + real render 防抖

  Ver 1.3.6 | 阅读器 v6 — 多分辨率缓存 + bisect 页码追踪 + 欢迎页 overlay
    - 缩放性能重写：移除所有 PdfReaderWidget._cache.clear() 调用
      · 多分辨率缓存：不同 zoom_key 的页面共存于 dict 中
      · zoom 切换时只渲染缓存未命中的页面，已缓存直接复用
      · 缓存上限 3000 entries LRU
    - 页码追踪：bisect_right（Python C 级实现）在 _page_heights 排序数组上二分查找
      · 100ms timer，O(log n)，379 页查找 <1μs
    - 欢迎页重写：作为 self 的子 widget 覆盖在 scroll_area 上方
      · showEvent 触发显示，不受 viewport 尺寸影响
      · _destroy_welcome 确保关闭 PDF 时清理
    - 关闭 PDF：page_container.setFixedSize(0,0) 彻底移除滚动条
    - 缩放步长：+/- 按钮 5%，触控板 pinch 每 120 angle units = 5%
    - fit_width/fit_height 不再清空缓存

  Ver 1.3.7 | 二阶段缩放完整实现 + 整数缓存键 + 捏合终止检测
    - **完整二阶段缩放流水线**：
      · Pass 1（即时）：`_smooth_scale_all()` 对现有 QPixmap 做 SmoothTransformation 缩放
        — <1ms 视觉反馈，用户立即看到页面大小变化
      · Pass 2（延迟）：180ms `QTimer.singleShot` → `_sharp_render()` PyMuPDF 真实渲染
        — 高清画质自动替换模糊图
    - **快速缓存探测**：Pass 2 调度前检查是否所有页面已缓存，若是则完全跳过重渲染
    - **整数百分比舍入**：`int(round(pct))` 确保 101%和 101.4% 共享同一缓存键
    - **连续捏合优化**：`skip_deferred=True` 在手势期间仅做即时缩放，不触发后台渲染
    - **捏合终止检测**：`ScrollEnd (phase=3)` → 触发 `_sharp_render` 产生最终高清画面
    - BUGFIX: `_show_welcome` 重复居中代码 + `vw`/`vh` 未定义变量名

  Ver 1.3.8 | LRU 缓存 + 内存水位线 + 双 timer 页码追踪 + 按需预加载
    - 缓存替换为 collections.OrderedDict（LRU 有序淘汰）：
      · `_cache_put`: 插入时 `move_to_end`，超 250MB 限制时 `popitem(last=False)`
      · `_cache_get`: 命中时 `move_to_end`（最近使用标记）
      · 驻留特权：`zk in ("fh","fw")` 永不被淘汰（fit_width/fit_height for page 0）
      · `_cache_memory_bytes` 实时追踪，`_clear_cache()` 清零
      · 删除旧 `MAX_CACHE=3000` 条目上限，改为内存驱动
    - 双 timer 页码追踪：
      · Throttle (30ms): `_do_throttle_page` — `scrollY / avgPageHeight` 粗略页码，<1μs
      · Debounce (150ms): `_do_debounce_calibration` — `bisect_right` 精确校准
      · 滚动停止后自动触发 `_prefetch_around(N)` 预加载 N±1 页
    - 快速缓存探测：`_set_zoom_pct` 仅检查 page 0 是否命中，不再遍历所有页面
    - `_sharp_render` 改用 `_cache_get`（LRU 语义），`finally` 清除 `_pending_zoom_pct`
    - `_cancel_deferred_renders` 统一停止所有 timer
    - BUGFIX: 滚动→闪退 — `_on_scrollbar_changed` + throttle/debounce 双重守卫

  Ver 1.3.9 | 缩放比例计算修正
    - **删除 `_smooth_scale_all`** — 该方法使用 `_fw_ratio` 作为缩放基数，
      但 pixmap 可能处于任意缩放级别（fit_height/fit_width/任意%）。
      从 fit_height(83%) 缩放至 150% 时，计算出 scale=1.5/2.0=0.75 — 缩小而非放大
    - **三处缩放路径重写为正确的相对比例**：
      · `_set_zoom_pct`: 在修改 `self._zoom_mode` 前保存 `old_pct`，
        计算 `scale = new_factor / old_factor`
      · `_apply_fit_mode`: 同样先存旧值再算比值
      · `_on_resize`: 使用旧 `_fw_ratio/_fh_ratio` 计算旧因子
    - 所有缩放路径统一：old_pct → old_factor, new_factor, scale = new/old
    - BUGFIX: 点 +/- 按钮页面反向缩放或不变 — 缩放基数错误导致方向反转
