"""i18n — translation dict for PDFeverything GUI. All UI strings go through `tr()`."""

from PyQt6.QtCore import QSettings

# ── Master translation table ──────────────────────────────

T = {
    # ── Window ──
    "window_title":           {"zh": "PDFeverything",                             "en": "PDFeverything"},
    "tab_merge":              {"zh": "📦 合并与转换",                              "en": "📦 Merge & Convert"},
    "tab_tools":              {"zh": "🔧 PDF 工具",                                "en": "🔧 PDF Tools"},

    # ── File menu ──
    "menu_file":              {"zh": "文件(&F)",                                   "en": "&File"},
    "menu_add_files":         {"zh": "添加文件...",                                 "en": "Add Files..."},
    "menu_clear_list":        {"zh": "清空列表",                                    "en": "Clear List"},
    "menu_quit":              {"zh": "退出(&Q)",                                   "en": "&Quit"},

    # ── Operations menu ──
    "menu_operations":        {"zh": "操作(&O)",                                   "en": "&Operations"},
    "menu_settings":          {"zh": "设置(&S)",                                   "en": "&Settings"},
    "menu_language":          {"zh": "语言(&L)",                                   "en": "&Language"},
    "menu_lang_zh":           {"zh": "中文",                                       "en": "Chinese"},
    "menu_lang_en":           {"zh": "English",                                    "en": "English"},

    # ── Help menu ──
    "menu_help":              {"zh": "帮助(&H)",                                   "en": "&Help"},
    "menu_about":             {"zh": "关于",                                        "en": "About"},

    # ── Merge operations (group box) ──
    "group_merge_ops":        {"zh": "📦 合并操作",                                 "en": "📦 Merge Operations"},
    "btn_merge_unified":      {"zh": "🔀 合并为统一 PDF",                           "en": "🔀 Merge to Unified PDF"},
    "btn_images_to_pdf":      {"zh": "🖼️ 选中图片 → 生成 PDF",                     "en": "🖼️ Images → PDF"},
    "btn_word_to_pdf":        {"zh": "📝 选中 Word → 合并 PDF",                    "en": "📝 Word → Merge PDF"},

    # ── PDF operations ──
    "group_pdf_ops":          {"zh": "🔧 PDF 操作（选中列表中的 PDF）",             "en": "🔧 PDF Operations (selected PDFs)"},
    "btn_split":              {"zh": "✂️ 拆分",                                    "en": "✂️ Split"},
    "btn_compress":           {"zh": "🗜️ 压缩",                                    "en": "🗜️ Compress"},
    "btn_watermark":          {"zh": "💧 水印",                                    "en": "💧 Watermark"},
    "btn_encrypt":            {"zh": "🔒 加密",                                    "en": "🔒 Encrypt"},
    "btn_decrypt":            {"zh": "🔓 解密",                                    "en": "🔓 Decrypt"},
    "btn_rotate":             {"zh": "🔄 旋转",                                    "en": "🔄 Rotate"},
    "btn_info":               {"zh": "ℹ️ 信息",                                    "en": "ℹ️ Info"},

    # ── Output path row ──
    "label_output":           {"zh": "输出路径:",                                   "en": "Output:"},
    "btn_browse":             {"zh": "浏览...",                                     "en": "Browse..."},

    # ── Tab 2 tools ──
    "tool_extract_text":      {"zh": "📄 PDF 提取文字",                             "en": "📄 Extract Text from PDF"},
    "tool_extract_images":    {"zh": "🖼️ PDF 提取图片",                             "en": "🖼️ Extract Images from PDF"},
    "tool_pdf_to_images":     {"zh": "🖼️ PDF → 图片",                               "en": "🖼️ PDF → Images"},
    "tool_images_to_pdf":     {"zh": "📄 图片 → PDF",                               "en": "📄 Images → PDF"},
    "tool_to_word":           {"zh": "📝 PDF → Word",                               "en": "📝 PDF → Word"},
    "tool_to_ppt":            {"zh": "📊 PDF → PowerPoint",                         "en": "📊 PDF → PowerPoint"},
    "tool_to_excel":          {"zh": "📈 PDF → Excel",                              "en": "📈 PDF → Excel"},

    # ── Reader tab ──
    "tab_reader":             {"zh": "📖 阅读",                                      "en": "📖 Reader"},
    "reader_scroll":          {"zh": "连续",                                        "en": "Scroll"},
    "reader_grid":            {"zh": "网格",                                        "en": "Grid"},
    "reader_scroll_tip":      {"zh": "连续垂直滚动（默认）",                           "en": "Continuous vertical scroll (default)"},
    "reader_grid_tip":        {"zh": "缩略图网格浏览",                                "en": "Thumbnail grid view"},
    "reader_prev":            {"zh": "上一页",                                       "en": "Prev"},
    "reader_next":            {"zh": "下一页",                                       "en": "Next"},
    "reader_fit_width":       {"zh": "适应宽度",                                      "en": "Fit Width"},
    "reader_fit_height":      {"zh": "适应高度",                                      "en": "Fit Height"},
    "reader_zoom_out":        {"zh": "缩小 5%",                                      "en": "Zoom out 5%"},
    "reader_zoom_in":         {"zh": "放大 5%",                                      "en": "Zoom in 5%"},
    "reader_zoom_edit":       {"zh": "点击输入缩放比例 (50-500)",                      "en": "Click to type zoom % (50-500)"},
    "reader_fit_width_tip":   {"zh": "将页面宽度缩放至窗口宽度",                         "en": "Fit page width to viewport"},
    "reader_fit_height_tip":  {"zh": "将页面高度缩放至窗口高度",                         "en": "Fit page height to viewport"},
    "reader_zoom_tip":        {"zh": "缩放级别",                                      "en": "Zoom level"},
    "reader_welcome":         {"zh": "打开 PDF 开始阅读",                              "en": "Open a PDF to start reading"},
    "reader_drop_here":       {"zh": "拖入 PDF 文件以阅读",                             "en": "Drop PDF here to read"},
    "reader_load_file":       {"zh": "加载文件",                                       "en": "Load file..."},
    "reader_close":           {"zh": "关闭此文档",                                     "en": "Close this document"},
    "reader_edit":            {"zh": "✎ 编辑",                                       "en": "✎ Edit"},
    "reader_editing":         {"zh": "✎ 编辑中",                                     "en": "✎ Editing"},
    "reader_edit_select":     {"zh": "☝ 选择",                                       "en": "☝ Select"},
    "reader_edit_rotate":     {"zh": "↻ 旋转90°",                                    "en": "↻ Rotate 90°"},
    "reader_edit_delete":     {"zh": "✕ 删除",                                       "en": "✕ Delete"},
    "reader_edit_extract":    {"zh": "📄 提取合并",                                   "en": "📄 Extract"},
    "reader_edit_export":     {"zh": "💾 导出",                                       "en": "💾 Export"},
    "reader_edit_undo":       {"zh": "↩ 撤销",                                       "en": "↩ Undo"},
    "reader_edit_redo":       {"zh": "↪ 重做",                                       "en": "↪ Redo"},
    "reader_cannot_open":     {"zh": "无法打开: {}",                                  "en": "Cannot open: {}"},
    "reader_encrypted":       {"zh": "此 PDF 受密码保护",                               "en": "This PDF is password-protected"},
    "reader_open_pdf":        {"zh": "打开 PDF...",                                  "en": "Open PDF..."},
    "reader_file_filter":     {"zh": "PDF 文件 (*.pdf);;所有文件 (*)",                "en": "PDF files (*.pdf);;All files (*)"},

    # ── Status bar ──
    "status_ready":           {"zh": "就绪",                                        "en": "Ready"},
    "status_done":            {"zh": "✅ 完成",                                      "en": "✅ Done"},
    "status_error":           {"zh": "❌ 错误",                                      "en": "❌ Error"},
    "status_cancelled":       {"zh": "⏹️ 已取消",                                   "en": "⏹️ Cancelled"},
    "btn_cancel":             {"zh": "取消",                                        "en": "Cancel"},

    # ── Progress messages ──
    "progress_merging":       {"zh": "合并中 ({}/{}): {}",                           "en": "Merging ({}/{}): {}"},
    "progress_converting":    {"zh": "转换中 ({}/{}): {}",                           "en": "Converting ({}/{}): {}"},

    # ── Dialogs: titles ──
    "dlg_encrypt_title":      {"zh": "🔒 加密 PDF",                                 "en": "🔒 Encrypt PDF"},
    "dlg_decrypt_title":      {"zh": "🔓 解密 PDF",                                 "en": "🔓 Decrypt PDF"},
    "dlg_watermark_title":    {"zh": "💧 添加水印",                                 "en": "💧 Add Watermark"},
    "dlg_rotate_title":       {"zh": "🔄 旋转页面",                                 "en": "🔄 Rotate Pages"},
    "dlg_compress_title":     {"zh": "🗜️ 压缩 PDF",                                 "en": "🗜️ Compress PDF"},
    "dlg_split_title":        {"zh": "✂️ 拆分 PDF",                                 "en": "✂️ Split PDF"},
    "dlg_info_title":         {"zh": "ℹ️ PDF 信息",                                  "en": "ℹ️ PDF Info"},

    # ── Dialogs: encrypt ──
    "label_password":         {"zh": "密码:",                                        "en": "Password:"},
    "label_confirm_pw":       {"zh": "确认密码:",                                    "en": "Confirm:"},
    "placeholder_password":   {"zh": "输入密码",                                     "en": "Enter password"},
    "placeholder_confirm":    {"zh": "再次输入密码",                                  "en": "Re-enter password"},
    "msg_pw_empty":           {"zh": "密码不能为空",                                  "en": "Password cannot be empty"},
    "msg_pw_mismatch":        {"zh": "两次输入的密码不一致",                           "en": "Passwords do not match"},
    "msg_pw_wrong":           {"zh": "密码不正确，无法解密",                           "en": "Wrong password, cannot decrypt"},

    # ── Dialogs: watermark ──
    "wm_type_label":          {"zh": "水印类型:",                                    "en": "Watermark type:"},
    "wm_type_text":           {"zh": "文字水印",                                     "en": "Text watermark"},
    "wm_type_pdf":            {"zh": "PDF 水印",                                     "en": "PDF watermark"},
    "wm_group_text":          {"zh": "文字水印设置",                                  "en": "Text Watermark Settings"},
    "wm_group_pdf":           {"zh": "PDF 水印设置",                                  "en": "PDF Watermark Settings"},
    "wm_text":                {"zh": "水印文字:",                                    "en": "Watermark text:"},
    "wm_font_size":           {"zh": "字体大小:",                                    "en": "Font size:"},
    "wm_opacity":             {"zh": "透明度:",                                      "en": "Opacity:"},
    "wm_rotation":            {"zh": "旋转角度:",                                    "en": "Rotation:"},
    "wm_placeholder_pdf":     {"zh": "选择水印 PDF 文件...",                          "en": "Select watermark PDF..."},
    "msg_wm_pdf_invalid":     {"zh": "请选择有效的水印 PDF 文件",                      "en": "Please select a valid watermark PDF file"},

    # ── Dialogs: rotate ──
    "rot_angle_label":        {"zh": "旋转角度:",                                    "en": "Angle:"},
    "rot_90_cw":              {"zh": "90° 顺时针",                                  "en": "90° CW"},
    "rot_90_ccw":             {"zh": "90° 逆时针",                                  "en": "90° CCW"},
    "rot_180":                {"zh": "180°",                                       "en": "180°"},
    "rot_all_pages":          {"zh": "所有页面",                                     "en": "All pages"},
    "rot_page_range":         {"zh": "页码范围:",                                    "en": "Page range:"},
    "rot_range_placeholder":  {"zh": "例: 1-5, 8, 10-12",                           "en": "e.g. 1-5, 8, 10-12"},
    "msg_rot_range_invalid":  {"zh": "页码范围无效: {}",                              "en": "Invalid page range: {}"},

    # ── Dialogs: compress ──
    "cmp_mode_label":         {"zh": "压缩模式:",                                    "en": "Compression mode:"},
    "cmp_lossless":           {"zh": "无损压缩（推荐）",                               "en": "Lossless (recommended)"},
    "cmp_medium":             {"zh": "中等压缩",                                     "en": "Medium"},
    "cmp_max":                {"zh": "最大压缩",                                     "en": "Maximum"},
    "cmp_info_text":          {"zh": "• 无损压缩: 保留原始质量，仅优化文件结构\n"
                                      "• 中等压缩: 轻微降低图片质量\n"
                                      "• 最大压缩: 会显著缩小文件但可能影响清晰度",
                               "en": "• Lossless: preserve quality, optimize structure only\n"
                                     "• Medium: slight image quality reduction\n"
                                     "• Maximum: smallest file, may affect clarity"},

    # ── Dialogs: split ──
    "spl_mode_label":         {"zh": "拆分方式:",                                    "en": "Split mode:"},
    "spl_mode_each":          {"zh": "每页拆分为一个文件",                             "en": "One file per page"},
    "spl_mode_by_n":          {"zh": "按页数拆分",                                    "en": "Every N pages"},
    "spl_mode_custom":        {"zh": "自定义范围",                                    "en": "Custom ranges"},
    "spl_group_by_n":         {"zh": "按页数拆分",                                    "en": "Split by page count"},
    "spl_group_custom":       {"zh": "自定义页码范围",                                "en": "Custom Page Ranges"},
    "spl_every":              {"zh": "每",                                          "en": "Every"},
    "spl_pages_unit":         {"zh": "页拆分为一个文件",                               "en": "pages per file"},
    "spl_range_placeholder":  {"zh": "每行一个范围，例如:\n1-5\n6-12\n13-20",         "en": "One range per line, e.g.:\n1-5\n6-12\n13-20"},
    "msg_spl_empty":          {"zh": "请输入页码范围",                                 "en": "Please enter page ranges"},
    "msg_spl_invalid":        {"zh": "范围格式无效: {}",                               "en": "Invalid range format: {}"},

    # ── Dialogs: info ──
    "info_label_path":        {"zh": "文件路径",                                     "en": "File path"},
    "info_label_pages":       {"zh": "页数",                                        "en": "Pages"},
    "info_label_size":        {"zh": "文件大小",                                     "en": "File size"},
    "info_label_encrypted":   {"zh": "是否加密",                                     "en": "Encrypted"},
    "info_label_title":       {"zh": "标题",                                        "en": "Title"},
    "info_label_author":      {"zh": "作者",                                        "en": "Author"},
    "info_label_subject":     {"zh": "主题",                                        "en": "Subject"},
    "info_label_creator":     {"zh": "创建者",                                       "en": "Creator"},
    "info_label_producer":    {"zh": "生成工具",                                     "en": "Producer"},
    "info_yes":               {"zh": "是",                                         "en": "Yes"},
    "info_no":                {"zh": "否",                                         "en": "No"},
    "info_na":                {"zh": "N/A",                                       "en": "N/A"},

    # ── File list widget ──
    "fl_btn_add":             {"zh": "📂 添加文件",                                  "en": "📂 Add Files"},
    "fl_btn_remove":          {"zh": "🗑️ 移除",                                     "en": "🗑️ Remove"},
    "fl_btn_clear":           {"zh": "✖️ 清空",                                     "en": "✖️ Clear All"},
    "fl_btn_up_tip":          {"zh": "上移",                                        "en": "Move up"},
    "fl_btn_down_tip":        {"zh": "下移",                                        "en": "Move down"},
    "fl_menu_remove":         {"zh": "🗑️ 移除",                                     "en": "🗑️ Remove"},
    "fl_menu_top":            {"zh": "⬆ 移到最前",                                  "en": "⬆ Move to top"},
    "fl_menu_bottom":         {"zh": "⬇ 移到最后",                                  "en": "⬇ Move to bottom"},
    "fl_dialog_title":        {"zh": "选择文件",                                     "en": "Select Files"},
    "fl_dialog_filter":       {"zh": "所有支持的文件 (*.pdf *.png *.jpg *.jpeg *.gif *.bmp *.tiff "
                                      "*.webp *.docx *.doc *.rtf *.pptx *.ppt *.xlsx *.xls *.csv "
                                      "*.txt *.md *.log *.py *.json *.xml *.html *.yaml *.ini *.sh);;"
                                      "所有文件 (*)",
                               "en": "All supported files (*.pdf *.png *.jpg *.jpeg *.gif *.bmp *.tiff "
                                     "*.webp *.docx *.doc *.rtf *.pptx *.ppt *.xlsx *.xls *.csv "
                                     "*.txt *.md *.log *.py *.json *.xml *.html *.yaml *.ini *.sh);;"
                                     "All files (*)"},
    "fl_msg_skip_title":      {"zh": "提示",                                        "en": "Notice"},
    "fl_msg_skip_body":       {"zh": "已跳过 {count} 个不支持的文件格式。\n"
                                      "支持格式: PDF, 图片, Word, PPT, Excel, 文本文件",
                               "en": "Skipped {count} unsupported file format(s).\n"
                                     "Supported: PDF, Images, Word, PPT, Excel, Text files"},

    # ── Main window messages ──
    "msg_no_files":           {"zh": "请先添加文件到列表",                              "en": "Please add files to the list first"},
    "msg_no_images":          {"zh": "列表中未发现图片文件",                             "en": "No image files found in the list"},
    "msg_no_word":            {"zh": "列表中未发现 Word 文档",                          "en": "No Word documents found in the list"},
    "msg_partial_fail":       {"zh": "成功转换 {converted}/{total} 个文件。\n\n"
                                      "以下文件未能转换:\n{failed_list}",
                               "en": "Converted {converted} of {total} files.\n\n"
                                     "Failed:\n{failed_list}"},
    "msg_merge_done":         {"zh": "已成功处理 {count} 个文件。\n输出: {output}",
                               "en": "Processed {count} file(s).\nOutput: {output}"},
    "msg_compress_done":      {"zh": "原始大小: {before}\n压缩后: {after}\n减小: {ratio:.1f}%",
                               "en": "Original: {before}\nCompressed: {after}\nReduction: {ratio:.1f}%"},
    "msg_done_count":         {"zh": "已成功处理，共 {count} 项。",                     "en": "Processed {count} item(s)."},
    "msg_done_files":         {"zh": "已生成 {count} 个文件。",                         "en": "Generated {count} file(s)."},
    "msg_op_failed":          {"zh": "操作失败",                                      "en": "Operation failed"},

    # ── Dialogs: save/select ──
    "dlg_save_pdf":           {"zh": "保存输出文件",                                   "en": "Save output file"},
    "dlg_save_text":          {"zh": "保存文本文件",                                   "en": "Save text file"},
    "dlg_select_pdf":         {"zh": "选择 PDF 文件",                                 "en": "Select PDF file"},
    "dlg_select_output_dir":  {"zh": "选择输出目录",                                   "en": "Select output directory"},
    "dlg_select_images":      {"zh": "选择图片",                                      "en": "Select images"},
    "file_filter_pdf":        {"zh": "PDF 文件 (*.pdf)",                             "en": "PDF files (*.pdf)"},
    "file_filter_text":       {"zh": "文本文件 (*.txt)",                               "en": "Text files (*.txt)"},
    "file_filter_images":     {"zh": "图片文件 (*.png *.jpg *.jpeg *.gif *.bmp *.tiff *.webp);;"
                                      "所有文件 (*)",
                               "en": "Image files (*.png *.jpg *.jpeg *.gif *.bmp *.tiff *.webp);;"
                                     "All files (*)"},

    # ── Office status ──
    "office_checking":        {"zh": "检测中...",                                     "en": "Checking..."},
    "office_status_fmt":      {"zh": "Office 状态: {word} | {ppt} | {excel}"
                                      "\n（❌ 时将使用纯 Python 渲染，保文本但舍格式）",
                               "en": "Office status: {word} | {ppt} | {excel}"
                                     "\n(❌ = fallback Python renderer, text preserved but formatting lost)"},
    "office_ok":              {"zh": "✅",                                          "en": "OK"},
    "office_fail":            {"zh": "❌",                                          "en": "N/A"},

    # ── About dialog ──
    "about_title":            {"zh": "关于 PDFeverything",                           "en": "About PDFeverything"},
    "about_text":             {"zh": "PDFeverything v1.4.0\n\n"
                                      "一站式 PDF 处理桌面应用\n"
                                      "支持合并、拆分、格式转换、混合文件合并、PDF 阅读器等\n\n"
                                      "技术栈: Python + PyQt6 + PyMuPDF\n"
                                      "© 2026",
                               "en": "PDFeverything v1.4.0\n\n"
                                     "All-in-one PDF processing desktop app\n"
                                     "Merge, split, convert, mix files, built-in PDF reader and more\n\n"
                                     "Tech: Python + PyQt6 + PyMuPDF\n"
                                     "© 2026"},

    # ── Default output filename ──
    "default_output":         {"zh": "output.pdf",                                  "en": "output.pdf"},
    "default_merged":         {"zh": "merged.pdf",                                  "en": "merged.pdf"},
    "default_images":         {"zh": "images.pdf",                                  "en": "images.pdf"},
    "default_word_merged":    {"zh": "word_merged.pdf",                              "en": "word_merged.pdf"},

    # ── Watermark defaults ──
    "wm_default_text":        {"zh": "机密",                                        "en": "CONFIDENTIAL"},

    # ── Button dynamic labels ──
    "merge_pdf_files":        {"zh": "🔀 合并 PDF 文件",                              "en": "🔀 Merge PDF files"},
    "merge_image_files":      {"zh": "🖼️ 图片 → 合并 PDF",                           "en": "🖼️ Images → PDF"},
    "merge_word_files":       {"zh": "📝 Word → 合并 PDF",                           "en": "📝 Word → Merge PDF"},
    "merge_mixed_files":      {"zh": "🔀 混合文件 → 统一 PDF",                        "en": "🔀 Mixed files → Unified PDF"},
    "merge_as_pdf":           {"zh": "🔀 合并为 PDF",                                 "en": "🔀 Merge as PDF"},
}

# ── Tr helper ──────────────────────────────────────────────

_current_lang = None


def _load_lang() -> str:
    global _current_lang
    if _current_lang is None:
        s = QSettings("PDFeverything", "PDFeverything")
        _current_lang = s.value("language", "zh")
    return _current_lang


def tr(key: str, lang: str = None, **kwargs) -> str:
    """Translate a UI key. Falls back to key itself if missing."""
    if lang is None:
        lang = _load_lang()
    entry = T.get(key, {})
    text = entry.get(lang, entry.get("en", key))
    if kwargs:
        text = text.format(**kwargs)
    return text


def set_language(lang: str) -> None:
    """Persist language choice."""
    global _current_lang
    _current_lang = lang
    s = QSettings("PDFeverything", "PDFeverything")
    s.setValue("language", lang)


def current_language() -> str:
    return _load_lang()
