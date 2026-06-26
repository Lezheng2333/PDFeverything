#!/usr/bin/env python3
"""
PDFeverything — CLI 版本
========================
功能：合并、拆分、提取文本/图片、转换格式、压缩、加水印/加密等。

用法示例：
    python pdf_tool.py merge -i a.pdf b.pdf -o merged.pdf
    python pdf_tool.py split -i input.pdf -o out_dir/
    python pdf_tool.py extract-text -i input.pdf -o output.txt
    python pdf_tool.py extract-images -i input.pdf -o images/
    python pdf_tool.py to-images -i input.pdf -o images/ --dpi 200
    python pdf_tool.py compress -i input.pdf -o compressed.pdf
    python pdf_tool.py watermark -i input.pdf -w watermark.pdf -o watermarked.pdf
    python pdf_tool.py encrypt -i input.pdf -o encrypted.pdf --password secret
    python pdf_tool.py decrypt -i input.pdf -o decrypted.pdf --password secret
    python pdf_tool.py info -i input.pdf
    python pdf_tool.py rotate -i input.pdf -o rotated.pdf --angle 90

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

    except Exception as e:
        sys.exit(f"❌ 错误: {e}")


if __name__ == "__main__":
    main()
