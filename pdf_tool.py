#!/usr/bin/env python3
"""
PDFeverything — CLI 版本
========================
功能：合并、拆分、提取、格式互转、压缩、加水印/加密等。

用法示例：
    python pdf_tool.py merge -i a.pdf b.pdf -o merged.pdf
    python pdf_tool.py split -i input.pdf -o out_dir/
    python pdf_tool.py extract-text -i input.pdf -o output.txt
    python pdf_tool.py compress -i input.pdf -o compressed.pdf
    python pdf_tool.py to-word -i input.pdf -o output.docx
    python pdf_tool.py to-ppt -i input.pdf -o output.pptx
    python pdf_tool.py to-excel -i input.pdf -o output.xlsx

核心逻辑由 core.pdf_ops.PdfOperator 提供，CLI 和 GUI 共享同一实现。
"""

import argparse
import sys
from pathlib import Path

from core.pdf_ops import PdfOperator
from core.utils import format_bytes, parse_page_ranges

# ── CLI 入口 ────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(
        description="PDFeverything — 合并/拆分/提取/转换/压缩/水印/加密",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    sub = parser.add_subparsers(dest="command", help="操作命令")

    # --- mixed-merge（混合文件 → 统一 PDF，GUI/ MCP 之外补齐 CLI 通道）---
    p_mix = sub.add_parser("mixed-merge", help="混合文件（PDF/图片/Office/文本）合并为统一 PDF")
    p_mix.add_argument("-i", "--input", nargs="+", required=True,
                       help="输入文件（支持 PDF、图片、Word、PPT、Excel、文本）")
    p_mix.add_argument("-o", "--output", required=True, help="输出 PDF 文件")
    p_mix.add_argument("--json", action="store_true", help="JSON 输出")

    # --- search ---
    p_search = sub.add_parser("search", help="在 PDF 中查找文本")
    p_search.add_argument("-i", "--input", required=True, help="输入 PDF 文件")
    p_search.add_argument("-q", "--query", required=True, help="要查找的文本")
    p_search.add_argument("-o", "--output", help="结果输出文件 (.json 或 .txt)")
    p_search.add_argument("--case", action="store_true", help="区分大小写")
    p_search.add_argument("--whole-word", action="store_true", help="仅整词匹配")
    p_search.add_argument("--pages", help="限定范围: all / 1-5 / 1,3,5")
    p_search.add_argument("--json", action="store_true", help="JSON 输出到终端")

    # --- outline ---
    p_outline = sub.add_parser("outline", help="导出 PDF 目录（书签）")
    p_outline.add_argument("-i", "--input", required=True, help="输入 PDF 文件")
    p_outline.add_argument("--json", action="store_true", help="JSON 输出")

    # --- info ---
    p_info = sub.add_parser("info", help="查看 PDF 信息")
    p_info.add_argument("-i", "--input", required=True, help="输入 PDF 文件")

    # --- merge ---
    p_merge = sub.add_parser("merge", help="合并多个 PDF")
    p_merge.add_argument("-i", "--input", nargs="+", required=True,
                         help="输入 PDF 文件（可多个）")
    p_merge.add_argument("-o", "--output", required=True, help="输出 PDF 文件")

    # --- split ---
    p_split = sub.add_parser("split", help="拆分为单页 PDF")
    p_split.add_argument("-i", "--input", required=True, help="输入 PDF 文件")
    p_split.add_argument("-o", "--output", required=True, help="输出目录")

    # --- extract-text ---
    p_text = sub.add_parser("extract-text", help="提取纯文本")
    p_text.add_argument("-i", "--input", required=True, help="输入 PDF 文件")
    p_text.add_argument("-o", "--output", required=True, help="输出文本文件")

    # --- extract-images ---
    p_imgs = sub.add_parser("extract-images", help="提取嵌入图片")
    p_imgs.add_argument("-i", "--input", required=True, help="输入 PDF 文件")
    p_imgs.add_argument("-o", "--output", required=True, help="输出目录")

    # --- to-images ---
    p_ti = sub.add_parser("to-images", help="PDF 每页转图片")
    p_ti.add_argument("-i", "--input", required=True, help="输入 PDF 文件")
    p_ti.add_argument("-o", "--output", required=True, help="输出目录")
    p_ti.add_argument("--dpi", type=int, default=200,
                      help="图片分辨率 36-1200 (默认 200)")

    # --- from-images ---
    p_fi = sub.add_parser("from-images", help="多张图片合并为 PDF")
    p_fi.add_argument("-i", "--input", nargs="+", required=True,
                      help="输入图片文件（可多个）")
    p_fi.add_argument("-o", "--output", required=True, help="输出 PDF 文件")

    # --- compress ---
    p_comp = sub.add_parser("compress", help="压缩 PDF")
    p_comp.add_argument("-i", "--input", required=True, help="输入 PDF 文件")
    p_comp.add_argument("-o", "--output", required=True, help="输出压缩后的 PDF")
    p_comp.add_argument("--mode", choices=["lossless", "medium", "max"],
                        default="lossless",
                        help="压缩档位: lossless 无损 / medium 中等 / max 最大")

    # --- watermark ---
    p_wm = sub.add_parser("watermark", help="添加水印")
    p_wm.add_argument("-i", "--input", required=True, help="输入 PDF 文件")
    p_wm.add_argument("-w", "--watermark", required=True, help="水印 PDF 文件")
    p_wm.add_argument("-o", "--output", required=True, help="输出 PDF 文件")

    # --- encrypt ---
    p_enc = sub.add_parser("encrypt", help="加密 PDF（设置密码）")
    p_enc.add_argument("-i", "--input", required=True, help="输入 PDF 文件")
    p_enc.add_argument("-o", "--output", required=True, help="输出加密后的 PDF")
    p_enc.add_argument("--password", required=True, help="打开密码")

    # --- decrypt ---
    p_dec = sub.add_parser("decrypt", help="解密 PDF（移除密码）")
    p_dec.add_argument("-i", "--input", required=True, help="输入加密的 PDF")
    p_dec.add_argument("-o", "--output", required=True, help="输出解密后的 PDF")
    p_dec.add_argument("--password", required=True, help="打开密码")

    # --- rotate ---
    p_rot = sub.add_parser("rotate", help="旋转页面")
    p_rot.add_argument("-i", "--input", required=True, help="输入 PDF 文件")
    p_rot.add_argument("-o", "--output", required=True, help="输出 PDF 文件")
    p_rot.add_argument("--angle", type=int, required=True,
                       choices=[90, 180, 270], help="旋转角度")
    p_rot.add_argument("--pages", type=int, nargs="*",
                       help="目标页码（默认全部）")

    # --- to-word ---
    p_tw = sub.add_parser("to-word", help="PDF 转 Word")
    p_tw.add_argument("-i", "--input", required=True, help="输入 PDF 文件")
    p_tw.add_argument("-o", "--output", required=True, help="输出 .docx 文件")

    # --- to-ppt ---
    p_tp = sub.add_parser("to-ppt", help="PDF 转 PowerPoint")
    p_tp.add_argument("-i", "--input", required=True, help="输入 PDF 文件")
    p_tp.add_argument("-o", "--output", required=True, help="输出 .pptx 文件")
    p_tp.add_argument("--dpi", type=int, default=200,
                      help="图片分辨率 36-1200 (默认 200)")

    # --- to-excel ---
    p_te = sub.add_parser("to-excel", help="PDF 转 Excel（提取表格）")
    p_te.add_argument("-i", "--input", required=True, help="输入 PDF 文件")
    p_te.add_argument("-o", "--output", required=True, help="输出 .xlsx 文件")

    # --- page-numbers / metadata / nup / insert ---
    p_pn = sub.add_parser("add-page-numbers", help="添加页码/页眉页脚")
    p_pn.add_argument("-i", "--input", required=True)
    p_pn.add_argument("-o", "--output", required=True)
    p_pn.add_argument("--position", default="bottom-center",
                      choices=["bottom-center", "bottom-left", "bottom-right",
                               "top-center", "top-left", "top-right"])
    p_pn.add_argument("--template", default="{n}",
                      help="支持 {n} 当前序号 / {total} 总页数 / {page} 原始页码")
    p_pn.add_argument("--start", type=int, default=1, help="起始编号 (默认 1)")
    p_pn.add_argument("--font-size", type=int, default=10)
    p_pn.add_argument("--margin", type=float, default=28.0)
    p_pn.add_argument("--pages", help="限定页面: all / 1-5 / 1,3,5")
    p_pn.add_argument("--json", action="store_true")

    p_md = sub.add_parser("set-metadata", help="修改 PDF 元数据（标题/作者等）")
    p_md.add_argument("-i", "--input", required=True)
    p_md.add_argument("-o", "--output", required=True)
    p_md.add_argument("--title")
    p_md.add_argument("--author")
    p_md.add_argument("--subject")
    p_md.add_argument("--keywords")
    p_md.add_argument("--creator")
    p_md.add_argument("--producer")
    p_md.add_argument("--json", action="store_true")

    p_nup = sub.add_parser("nup", help="N 页拼版到一张纸（省纸打印）")
    p_nup.add_argument("-i", "--input", required=True)
    p_nup.add_argument("-o", "--output", required=True)
    p_nup.add_argument("--per-sheet", type=int, default=2,
                       choices=[2, 4, 6, 8, 9, 16], help="每张纸页数 (默认 2)")
    p_nup.add_argument("--paper", default="a4", choices=["a4", "a3", "letter"])
    p_nup.add_argument("--json", action="store_true")

    p_ins = sub.add_parser("insert-pages", help="把另一个 PDF 插入到指定位置")
    p_ins.add_argument("-i", "--input", required=True, help="目标 PDF")
    p_ins.add_argument("-s", "--source", required=True, help="要插入的 PDF")
    p_ins.add_argument("-o", "--output", required=True)
    p_ins.add_argument("--at", type=int, default=-1,
                       help="插入位置（1-based，默认追加到末尾）")
    p_ins.add_argument("--json", action="store_true")

    p_ex = sub.add_parser("extract-pages-fitz", help="抽取页面为新 PDF（PyMuPDF 实现）")
    p_ex.add_argument("-i", "--input", required=True)
    p_ex.add_argument("-o", "--output", required=True)
    p_ex.add_argument("--pages", required=True)
    p_ex.add_argument("--json", action="store_true")

    p_dl = sub.add_parser("delete-pages-fitz", help="删除页面（PyMuPDF 实现）")
    p_dl.add_argument("-i", "--input", required=True)
    p_dl.add_argument("-o", "--output", required=True)
    p_dl.add_argument("--pages", required=True)
    p_dl.add_argument("--json", action="store_true")

    # --- page editing ---
    p_del = sub.add_parser("delete-pages", help="删除指定页面")
    p_del.add_argument("-i", "--input", required=True)
    p_del.add_argument("-o", "--output",
                       help="输出 PDF（省略或与 -i 相同 = 就地修改，可被 page-undo 撤销）")
    p_del.add_argument("--pages", required=True, help="1,3,5 或 1-5 或 all")
    p_del.add_argument("--json", action="store_true", help="JSON 输出")

    p_rotp = sub.add_parser("rotate-pages", help="旋转指定页面")
    p_rotp.add_argument("-i", "--input", required=True)
    p_rotp.add_argument("-o", "--output",
                       help="输出 PDF（省略或与 -i 相同 = 就地修改）")
    p_rotp.add_argument("--pages", required=True, help="1,3,5 或 1-5 或 all")
    p_rotp.add_argument("--degrees", type=int, required=True, choices=[90,180,270])
    p_rotp.add_argument("--json", action="store_true")

    p_mov = sub.add_parser("move-pages", help="移动页面到目标位置")
    p_mov.add_argument("-i", "--input", required=True)
    p_mov.add_argument("-o", "--output",
                       help="输出 PDF（省略或与 -i 相同 = 就地修改）")
    p_mov.add_argument("--source", required=True, help="1,2")
    p_mov.add_argument("--target", type=int, required=True, help="目标位置 (1-based)")
    p_mov.add_argument("--json", action="store_true")

    p_ext = sub.add_parser("extract-pages", help="提取所选页面到新PDF")
    p_ext.add_argument("-i", "--input", required=True)
    p_ext.add_argument("-o", "--output", required=True)
    p_ext.add_argument("--pages", required=True, help="1,3,5 或 1-5 或 all")
    p_ext.add_argument("--json", action="store_true")

    p_undo = sub.add_parser("page-undo", help="撤销上次页面编辑")
    p_undo.add_argument("-i", "--input", required=True)
    p_undo.add_argument("-o", "--output",
                       help="输出 PDF（省略或与 -i 相同 = 就地修改）")
    p_undo.add_argument("--json", action="store_true")

    p_redo = sub.add_parser("page-redo", help="重做上次撤销")
    p_redo.add_argument("-i", "--input", required=True)
    p_redo.add_argument("-o", "--output",
                       help="输出 PDF（省略或与 -i 相同 = 就地修改）")
    p_redo.add_argument("--json", action="store_true")

    p_hist = sub.add_parser("page-history", help="查看操作历史")
    p_hist.add_argument("-i", "--input", required=True)
    p_hist.add_argument("--json", action="store_true")

    p_list = sub.add_parser("page-list", help="列出所有页面状态")
    p_list.add_argument("-i", "--input", required=True)
    p_list.add_argument("--json", action="store_true")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    def _validate_dpi(value: int) -> int:
        if not 36 <= value <= 1200:
            sys.exit(f"❌ 错误: DPI 必须在 36-1200 之间，收到 {value}")
        return value

    def _emit(args, op: str, message: str, data=None):
        """统一的人类可读 / JSON 输出。"""
        if getattr(args, "json", False):
            import json as _json
            payload = {"success": True, "operation": op, "message": message}
            if data:
                payload["data"] = data
            print(_json.dumps(payload, ensure_ascii=False))
        else:
            print(f"✅ {message}")

    # 命令分发 — 全部委托给 PdfOperator
    try:
        if args.command == "mixed-merge":
            from core.merger import merge_mixed_files

            paths = [Path(p) for p in args.input]
            result = merge_mixed_files(paths, Path(args.output))
            if getattr(args, "json", False):
                import json
                print(json.dumps(result, ensure_ascii=False))
            else:
                print(f"✅ 已合并 {result['converted']}/{result['total_files']} 个文件 "
                      f"→ {args.output}")
                for f in result.get("failed", []):
                    print(f"  ⚠️  {Path(f['path']).name}: {f['reason']}")

        elif args.command == "search":
            from core.search import search_pdf

            pages = None
            if args.pages:
                pages = parse_page_ranges(args.pages, one_based=True)
            result = search_pdf(Path(args.input), args.query,
                                case_sensitive=args.case,
                                whole_word=args.whole_word,
                                pages=pages)
            if args.output:
                out_path = Path(args.output)
                if out_path.suffix.lower() == ".json":
                    import json
                    out_path.write_text(
                        json.dumps(result.as_dict(), ensure_ascii=False, indent=2),
                        encoding="utf-8")
                else:
                    lines = [f"# {result.query} — {result.count} matches "
                             f"on {len(result.pages_with_hits())} page(s)"]
                    for hit in result.hits:
                        lines.append(f"p.{hit.page + 1}\t{hit.context or hit.text}")
                    out_path.write_text("\n".join(lines), encoding="utf-8")
                print(f"✅ 找到 {result.count} 处 → {args.output}")
            elif args.json:
                import json
                print(json.dumps(result.as_dict(), ensure_ascii=False))
            else:
                if not result.count:
                    print(f"未找到「{result.query}」")
                else:
                    heads = ", ".join(str(p + 1) for p in result.pages_with_hits()[:20])
                    more = "…" if len(result.pages_with_hits()) > 20 else ""
                    print(f"找到 {result.count} 处，位于第 {heads}{more} 页"
                          + ("（已截断）" if result.truncated else ""))
                    for hit in result.hits[:30]:
                        print(f"  p.{hit.page + 1}  {hit.context or hit.text}")

        elif args.command == "outline":
            from core.search import get_outline

            entries = get_outline(Path(args.input))
            if args.json:
                import json
                print(json.dumps(
                    {"success": True, "count": len(entries),
                     "outline": [e.as_dict() for e in entries]},
                    ensure_ascii=False))
            else:
                if not entries:
                    print("(此文档没有书签目录)")
                for entry in entries:
                    for flat in entry.flatten():
                        indent = "  " * flat.level
                        page = f"  p.{flat.page + 1}" if flat.page >= 0 else ""
                        print(f"{indent}- {flat.title}{page}")

        elif args.command == "add-page-numbers":
            pages = (parse_page_ranges(args.pages, one_based=True)
                     if args.pages else None)
            count = PdfOperator.add_page_numbers(
                Path(args.input), Path(args.output), position=args.position,
                start_number=args.start, font_size=args.font_size,
                template=args.template, margin=args.margin, pages=pages)
            msg = f"已为 {count} 页添加页码 ({args.position})"
            _emit(args, "add-page-numbers", msg, {"pages": count})

        elif args.command == "set-metadata":
            fields = {k: v for k, v in (
                ("title", args.title), ("author", args.author),
                ("subject", args.subject), ("keywords", args.keywords),
                ("creator", args.creator), ("producer", args.producer)) if v is not None}
            result = PdfOperator.set_metadata(Path(args.input), Path(args.output), fields)
            _emit(args, "set-metadata",
                  "已更新元数据: " + ", ".join(f"{k}={v}" for k, v in fields.items()),
                  {"metadata": result})

        elif args.command == "nup":
            sheets = PdfOperator.nup(Path(args.input), Path(args.output),
                                     per_sheet=args.per_sheet, paper=args.paper)
            _emit(args, "nup",
                  f"已拼版为 {sheets} 张（每张 {args.per_sheet} 页, {args.paper.upper()}）",
                  {"sheets": sheets})

        elif args.command == "insert-pages":
            inserted = PdfOperator.insert_pages(
                Path(args.input), Path(args.source), Path(args.output),
                at=None if args.at < 0 else args.at - 1)
            _emit(args, "insert-pages", f"已插入 {inserted} 页", {"inserted": inserted})

        elif args.command == "extract-pages-fitz":
            pages = parse_page_ranges(args.pages, one_based=True)
            count = PdfOperator.extract_pages(Path(args.input), Path(args.output), pages)
            _emit(args, "extract-pages-fitz", f"已提取 {count} 页", {"extracted": count})

        elif args.command == "delete-pages-fitz":
            pages = parse_page_ranges(args.pages, one_based=True)
            left = PdfOperator.delete_pages(Path(args.input), Path(args.output), pages)
            _emit(args, "delete-pages-fitz", f"已删除 {len(pages)} 页，剩余 {left} 页",
                  {"remaining": left})

        elif args.command == "info":
            info = PdfOperator.get_info(Path(args.input))
            print(f"文件: {info['path']}")
            print(f"页数: {info['pages']}")
            print(f"文件大小: {format_bytes(info['size_bytes'])}")
            print(f"是否加密: {'是' if info['encrypted'] else '否'}")
            print(f"标题: {info['title'] or 'N/A'}")
            print(f"作者: {info['author'] or 'N/A'}")
            print(f"主题: {info['subject'] or 'N/A'}")
            print(f"创建者: {info['creator'] or 'N/A'}")
            print(f"生成工具: {info['producer'] or 'N/A'}")

        elif args.command == "merge":
            paths = [Path(p) for p in args.input]
            PdfOperator.merge(paths, Path(args.output))
            print(f"✅ 已合并 {len(paths)} 个文件 → {args.output}")

        elif args.command == "split":
            outputs = PdfOperator.split(Path(args.input), Path(args.output))
            print(f"✅ 已拆分 {len(outputs)} 份 → {args.output}")

        elif args.command == "extract-text":
            PdfOperator.extract_text(Path(args.input), Path(args.output))
            print(f"✅ 文本已提取 → {args.output}")

        elif args.command == "extract-images":
            count = PdfOperator.extract_images(Path(args.input), Path(args.output))
            print(f"✅ 已提取 {count} 张图片 → {args.output}")

        elif args.command == "to-images":
            count = PdfOperator.to_images(Path(args.input), Path(args.output),
                                          dpi=_validate_dpi(args.dpi))
            print(f"✅ 已转换 {count} 页为图片 ({args.dpi} DPI) → {args.output}")

        elif args.command == "from-images":
            paths = [Path(p) for p in args.input]
            PdfOperator.from_images(paths, Path(args.output))
            print(f"✅ 已将 {len(paths)} 张图片合并 → {args.output}")

        elif args.command == "compress":
            result = PdfOperator.compress(Path(args.input), Path(args.output),
                                          mode=args.mode)
            print(f"✅ 压缩完成 [{args.mode}]: {result['before_bytes']:,} → "
                  f"{result['after_bytes']:,} 字节 ({result['ratio']:.1f}% 减小) "
                  f"→ {args.output}")

        elif args.command == "watermark":
            PdfOperator.watermark(Path(args.input), Path(args.watermark), Path(args.output))
            print(f"✅ 水印已添加 → {args.output}")

        elif args.command == "encrypt":
            PdfOperator.encrypt(Path(args.input), Path(args.output), args.password)
            print(f"✅ 已加密 → {args.output}")

        elif args.command == "decrypt":
            PdfOperator.decrypt(Path(args.input), Path(args.output), args.password)
            print(f"✅ 已解密 → {args.output}")

        elif args.command == "rotate":
            PdfOperator.rotate(Path(args.input), Path(args.output),
                               args.angle, args.pages)
            print(f"✅ 已旋转 → {args.output}")

        elif args.command == "to-word":
            pages = PdfOperator.to_word(Path(args.input), Path(args.output))
            print(f"✅ 已转换 {pages} 页 → {args.output}")

        elif args.command == "to-ppt":
            pages = PdfOperator.to_ppt(Path(args.input), Path(args.output),
                                       dpi=_validate_dpi(args.dpi))
            print(f"✅ 已转换 {pages} 页 → {args.output}")

        elif args.command == "to-excel":
            sheets = PdfOperator.to_excel(Path(args.input), Path(args.output))
            print(f"✅ 已提取 {sheets} 个工作表 → {args.output}")

        elif args.command in ("delete-pages", "rotate-pages", "move-pages",
                              "extract-pages", "page-undo", "page-redo",
                              "page-history", "page-list"):
            from core.page_editor import PdfPageEditor

            def _parse_pages(pages_str: str, total: int) -> list[int]:
                """页码范围 → 0-based 序号列表（复用 core.utils 的解析器）。"""
                try:
                    return parse_page_ranges(pages_str, total=total, one_based=True)
                except ValueError as e:
                    sys.exit(f"❌ 错误: {e}")

            def _json_output(success: bool, op: str, msg: str, data=None, error=None, code=None):
                import json
                out = {"success": success, "operation": op, "message": msg}
                if data: out["data"] = data
                if error: out.update({"error": error, "code": code})
                print(json.dumps(out, ensure_ascii=False))

            input_path = Path(args.input)
            # Omitting -o edits the file in place. That is not just convenience:
            # the undo journal is keyed to the document, so an in-place edit is
            # the only form the next `page-undo` invocation can still reverse.
            output_path = (Path(args.output)
                           if getattr(args, "output", None) else input_path)
            editor = PdfPageEditor(input_path)
            # Continue the session recorded by an earlier CLI call so
            # page-undo/page-redo/page-history actually have a history.
            editor.load_journal()

            if args.command == "page-list":
                import json
                pages = []
                for i in range(editor.page_count):
                    rotation = editor.page_rotation(i)
                    pages.append({"index": i + 1, "rotation": rotation})
                if getattr(args, "json", False):
                    print(json.dumps({"success": True, "operation": "list",
                                      "pageCount": editor.page_count, "pages": pages},
                                     ensure_ascii=False))
                else:
                    print(f"总页数: {editor.page_count}")
                    for p in pages:
                        rot = f" (旋转 {p['rotation']}°)" if p['rotation'] else ""
                        print(f"  第 {p['index']} 页{rot}")
                editor.close()
                return

            if args.command == "page-history":
                import json

                states = editor.history
                cursor = editor.history_cursor
                if getattr(args, "json", False):
                    print(json.dumps({"success": True, "operation": "history",
                                      "history": [s["desc"] for s in states],
                                      "cursor": cursor, "count": len(states)},
                                     ensure_ascii=False))
                else:
                    if not states:
                        print("  (空 — 还没有记录任何编辑)")
                    for i, item in enumerate(states):
                        marker = "  ← 当前" if i == cursor else ""
                        print(f"  {i + 1}. {item['desc'] or '(初始状态)'}{marker}")
                editor.close()
                return

            total = editor.page_count

            if args.command == "delete-pages":
                pages = _parse_pages(args.pages, total)
                if not pages:
                    editor.close()
                    sys.exit(f"❌ 错误: --pages 没有匹配任何页面 (共 {total} 页)")
                editor.delete_pages(pages)
                msg = f"已删除 {len(pages)} 页"
            elif args.command == "rotate-pages":
                pages = _parse_pages(args.pages, total)
                if not pages:
                    editor.close()
                    sys.exit(f"❌ 错误: --pages 没有匹配任何页面 (共 {total} 页)")
                editor.rotate_pages(pages, args.degrees)
                msg = f"已旋转 {len(pages)} 页 ({args.degrees}°)"
            elif args.command == "move-pages":
                source = _parse_pages(args.source, total)
                if not source:
                    editor.close()
                    sys.exit(f"❌ 错误: --source 没有匹配任何页面 (共 {total} 页)")
                target = args.target - 1
                editor.move_pages(source, target)
                msg = f"已移动 {len(source)} 页到位置 {args.target}"
            elif args.command == "extract-pages":
                pages = _parse_pages(args.pages, total)
                if not pages:
                    editor.close()
                    sys.exit(f"❌ 错误: --pages 没有匹配任何页面 (共 {total} 页)")
                editor.extract_pages(pages, output_path)
                editor.close()
                msg = f"已提取 {len(pages)} 页 → {output_path}"
                if getattr(args, "json", False):
                    _json_output(True, args.command, msg, {"extracted": len(pages)})
                else:
                    print(f"✅ {msg}")
                return
            elif args.command == "page-undo":
                desc = editor.undo()
                if not desc:
                    editor.close()
                    sys.exit("❌ 错误: 没有可撤销的操作（历史记录为空或已丢失）")
                msg = f"撤销: {desc}"
            elif args.command == "page-redo":
                desc = editor.redo()
                if not desc:
                    editor.close()
                    sys.exit("❌ 错误: 没有可重做的操作")
                msg = f"重做: {desc}"

            # Order matters: the journal must be recorded while the editor still
            # points at its input, otherwise saving to a new -o path would move
            # the journal key and the history would be written to a fresh journal
            # that the next invocation never reads.
            if args.command in ("delete-pages", "rotate-pages", "move-pages",
                                "page-undo", "page-redo"):
                editor.save_journal()
            if output_path and args.command != "extract-pages":
                editor.save(output_path)
            editor.close()

            if getattr(args, "json", False):
                _json_output(True, args.command, msg)
            else:
                print(f"✅ {msg}")

    except Exception as e:
        sys.exit(f"❌ 错误: {e}")


if __name__ == "__main__":
    main()
