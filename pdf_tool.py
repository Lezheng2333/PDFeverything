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
from core.utils import format_bytes

# ── CLI 入口 ────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(
        description="PDFeverything — 合并/拆分/提取/转换/压缩/水印/加密",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    sub = parser.add_subparsers(dest="command", help="操作命令")

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
    p_ti.add_argument("--dpi", type=int, default=200, help="图片分辨率 (默认 200)")

    # --- from-images ---
    p_fi = sub.add_parser("from-images", help="多张图片合并为 PDF")
    p_fi.add_argument("-i", "--input", nargs="+", required=True,
                      help="输入图片文件（可多个）")
    p_fi.add_argument("-o", "--output", required=True, help="输出 PDF 文件")

    # --- compress ---
    p_comp = sub.add_parser("compress", help="压缩 PDF")
    p_comp.add_argument("-i", "--input", required=True, help="输入 PDF 文件")
    p_comp.add_argument("-o", "--output", required=True, help="输出压缩后的 PDF")

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
    p_tp.add_argument("--dpi", type=int, default=200, help="图片分辨率 (默认 200)")

    # --- to-excel ---
    p_te = sub.add_parser("to-excel", help="PDF 转 Excel（提取表格）")
    p_te.add_argument("-i", "--input", required=True, help="输入 PDF 文件")
    p_te.add_argument("-o", "--output", required=True, help="输出 .xlsx 文件")

    # --- page editing ---
    p_del = sub.add_parser("delete-pages", help="删除指定页面")
    p_del.add_argument("-i", "--input", required=True)
    p_del.add_argument("-o", "--output", required=True)
    p_del.add_argument("--pages", required=True, help="1,3,5 或 1-5 或 all")
    p_del.add_argument("--json", action="store_true", help="JSON 输出")

    p_rotp = sub.add_parser("rotate-pages", help="旋转指定页面")
    p_rotp.add_argument("-i", "--input", required=True)
    p_rotp.add_argument("-o", "--output", required=True)
    p_rotp.add_argument("--pages", required=True, help="1,3,5 或 1-5 或 all")
    p_rotp.add_argument("--degrees", type=int, required=True, choices=[90,180,270])
    p_rotp.add_argument("--json", action="store_true")

    p_mov = sub.add_parser("move-pages", help="移动页面到目标位置")
    p_mov.add_argument("-i", "--input", required=True)
    p_mov.add_argument("-o", "--output", required=True)
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
    p_undo.add_argument("-o", "--output", required=True)
    p_undo.add_argument("--json", action="store_true")

    p_redo = sub.add_parser("page-redo", help="重做上次撤销")
    p_redo.add_argument("-i", "--input", required=True)
    p_redo.add_argument("-o", "--output", required=True)
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

    # 命令分发 — 全部委托给 PdfOperator
    try:
        if args.command == "info":
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
            count = PdfOperator.to_images(Path(args.input), Path(args.output), dpi=args.dpi)
            print(f"✅ 已转换 {count} 页为图片 ({args.dpi} DPI) → {args.output}")

        elif args.command == "from-images":
            paths = [Path(p) for p in args.input]
            PdfOperator.from_images(paths, Path(args.output))
            print(f"✅ 已将 {len(paths)} 张图片合并 → {args.output}")

        elif args.command == "compress":
            result = PdfOperator.compress(Path(args.input), Path(args.output))
            print(f"✅ 压缩完成: {result['before_bytes']:,} → {result['after_bytes']:,} "
                  f"字节 ({result['ratio']:.1f}% 减小) → {args.output}")

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
            pages = PdfOperator.to_ppt(Path(args.input), Path(args.output), dpi=args.dpi)
            print(f"✅ 已转换 {pages} 页 → {args.output}")

        elif args.command == "to-excel":
            sheets = PdfOperator.to_excel(Path(args.input), Path(args.output))
            print(f"✅ 已提取 {sheets} 个工作表 → {args.output}")

        elif args.command in ("delete-pages", "rotate-pages", "move-pages",
                              "extract-pages", "page-undo", "page-redo",
                              "page-history", "page-list"):
            from core.page_editor import PdfPageEditor

            def _parse_pages(pages_str: str, total: int) -> list[int]:
                """Parse page range string to 0-based ordinal list."""
                if pages_str.lower() == "all":
                    return list(range(total))
                result = []
                for part in pages_str.split(","):
                    part = part.strip()
                    if "-" in part:
                        a, b = part.split("-", 1)
                        result.extend(range(int(a) - 1, int(b)))
                    else:
                        result.append(int(part) - 1)
                return sorted(set(r for r in result if 0 <= r < total))

            def _json_output(success: bool, op: str, msg: str, data=None, error=None, code=None):
                import json
                out = {"success": success, "operation": op, "message": msg}
                if data: out["data"] = data
                if error: out.update({"error": error, "code": code})
                print(json.dumps(out, ensure_ascii=False))

            input_path = Path(args.input)
            output_path = Path(args.output) if hasattr(args, 'output') and args.output else None
            editor = PdfPageEditor(input_path)

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
                history = editor.undo_stack_desc
                if getattr(args, "json", False):
                    import json
                    print(json.dumps({"success": True, "operation": "history",
                                      "history": history, "count": len(history)},
                                     ensure_ascii=False))
                else:
                    for i, h in enumerate(reversed(history), 1):
                        print(f"  {i}. {h}")
                    if not history:
                        print("  (空)")
                editor.close()
                return

            total = editor.page_count

            if args.command == "delete-pages":
                pages = _parse_pages(args.pages, total)
                editor.delete_pages(pages)
                msg = f"已删除 {len(pages)} 页"
            elif args.command == "rotate-pages":
                pages = _parse_pages(args.pages, total)
                editor.rotate_pages(pages, args.degrees)
                msg = f"已旋转 {len(pages)} 页 ({args.degrees}°)"
            elif args.command == "move-pages":
                source = _parse_pages(args.source, total)
                target = args.target - 1
                editor.move_pages(source, target)
                msg = f"已移动 {len(source)} 页到位置 {args.target}"
            elif args.command == "extract-pages":
                pages = _parse_pages(args.pages, total)
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
                msg = f"撤销: {desc}" if desc else "无可撤销操作"
            elif args.command == "page-redo":
                desc = editor.redo()
                msg = f"重做: {desc}" if desc else "无可重做操作"

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
