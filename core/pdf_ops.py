"""PDF 核心操作 — 所有 PDF 处理方法的统一入口。

所有耗时方法接受可选的 progress_callback(msg: str, pct: int) 参数，
供 GUI Worker 和 CLI 共享使用。"""

import os
from pathlib import Path
from typing import Callable, List, Optional, Tuple

from .utils import check_input, ensure_output_dir


class PdfOperator:
    """PDF 操作静态方法集合。CLI 和 GUI 共用。"""

    # ── 1. 查看信息 ─────────────────────────────────────

    @staticmethod
    def get_info(input_path: Path) -> dict:
        """返回 PDF 元信息字典。"""
        from pypdf import PdfReader

        check_input(input_path)
        reader = PdfReader(input_path)
        info = reader.metadata or {}
        size = input_path.stat().st_size

        return {
            "path": str(input_path),
            "pages": len(reader.pages),
            "encrypted": reader.is_encrypted,
            "size_bytes": size,
            "title": (info.title or "") if info else "",
            "author": (info.author or "") if info else "",
            "subject": (info.subject or "") if info else "",
            "creator": (info.creator or "") if info else "",
            "producer": (info.producer or "") if info else "",
        }

    # ── 2. 合并 ────────────────────────────────────────

    @staticmethod
    def merge(
        input_paths: List[Path],
        output_path: Path,
        progress_callback: Optional[Callable[[str, int], None]] = None,
    ) -> None:
        """将多个 PDF 合并为一个。"""
        from pypdf import PdfWriter

        writer = PdfWriter()
        total = len(input_paths)
        for i, p in enumerate(input_paths):
            check_input(p)
            writer.append(p)
            if progress_callback:
                progress_callback(f"合并中 ({i+1}/{total}): {p.name}", int((i+1)/total*100))

        writer.write(output_path)
        writer.close()

    # ── 3. 拆分 ────────────────────────────────────────

    @staticmethod
    def split(
        input_path: Path,
        output_dir: Path,
        page_ranges: Optional[List[Tuple[int, int]]] = None,
        progress_callback: Optional[Callable[[str, int], None]] = None,
    ) -> List[Path]:
        """将 PDF 拆分为单页或多页文件。

        page_ranges: [(1,5), (6,10)] 表示拆成两个文件（页码范围 1-based 包含）。
        如果为 None，则每页拆成一个文件。
        """
        from pypdf import PdfReader, PdfWriter

        check_input(input_path)
        reader = PdfReader(input_path)
        out_dir = ensure_output_dir(output_dir)
        stem = input_path.stem
        total_pages = len(reader.pages)

        if page_ranges is None:
            page_ranges = [(i, i) for i in range(1, total_pages + 1)]

        outputs = []
        total_ranges = len(page_ranges)
        for ri, (start, end) in enumerate(page_ranges):
            writer = PdfWriter()
            start_idx = max(0, start - 1)
            end_idx = min(total_pages, end)
            for pi in range(start_idx, end_idx):
                writer.add_page(reader.pages[pi])

            if end_idx - start_idx == 1:
                fname = f"{stem}_p{start:04d}.pdf"
            else:
                fname = f"{stem}_p{start:04d}-{end:04d}.pdf"
            out_path = out_dir / fname
            with open(out_path, "wb") as f:
                writer.write(f)
            outputs.append(out_path)

            if progress_callback:
                progress_callback(f"拆分中 ({ri+1}/{total_ranges})", int((ri+1)/total_ranges*100))

        return outputs

    # ── 4. 提取文字 ───────────────────────────────────

    @staticmethod
    def extract_text(
        input_path: Path,
        output_path: Path,
        progress_callback: Optional[Callable[[str, int], None]] = None,
    ) -> str:
        """提取 PDF 纯文本并写入文件。返回完整文本。"""
        check_input(input_path)

        # 优先用 pdfplumber（更准确）
        try:
            import pdfplumber
            with pdfplumber.open(input_path) as pdf:
                all_text = []
                total = len(pdf.pages)
                for i, page in enumerate(pdf.pages, start=1):
                    text = page.extract_text()
                    if text:
                        all_text.append(f"--- 第 {i} 页 ---\n{text}")
                    if progress_callback:
                        progress_callback(f"提取文字 ({i}/{total})", int(i/total*100))
                content = "\n\n".join(all_text)
        except ImportError:
            from pypdf import PdfReader
            reader = PdfReader(input_path)
            all_text = []
            total = len(reader.pages)
            for i, page in enumerate(reader.pages, start=1):
                text = page.extract_text()
                if text:
                    all_text.append(f"--- 第 {i} 页 ---\n{text}")
                if progress_callback:
                    progress_callback(f"提取文字 ({i}/{total})", int(i/total*100))
            content = "\n\n".join(all_text)

        output_path.write_text(content, encoding="utf-8")
        return content

    # ── 5. 提取图片 ───────────────────────────────────

    @staticmethod
    def extract_images(
        input_path: Path,
        output_dir: Path,
        progress_callback: Optional[Callable[[str, int], None]] = None,
    ) -> int:
        """提取 PDF 中嵌入的图片。返回提取数量。"""
        import fitz  # PyMuPDF

        check_input(input_path)
        out_dir = ensure_output_dir(output_dir)
        doc = fitz.open(input_path)
        count = 0
        total = len(doc)
        for i, page in enumerate(doc, start=1):
            for j, img in enumerate(page.get_images(full=True), start=1):
                xref = img[0]
                base_image = doc.extract_image(xref)
                ext = base_image["ext"]
                img_path = out_dir / f"page{i:04d}_img{j:02d}.{ext}"
                img_path.write_bytes(base_image["image"])
                count += 1
            if progress_callback:
                progress_callback(f"提取图片 ({i}/{total})", int(i/total*100))
        doc.close()
        return count

    # ── 6. PDF → 图片 ─────────────────────────────────

    @staticmethod
    def to_images(
        input_path: Path,
        output_dir: Path,
        dpi: int = 200,
        progress_callback: Optional[Callable[[str, int], None]] = None,
    ) -> int:
        """将 PDF 每页转为 PNG 图片。返回页数。"""
        import fitz

        check_input(input_path)
        out_dir = ensure_output_dir(output_dir)
        stem = input_path.stem
        doc = fitz.open(input_path)
        total = len(doc)
        for i, page in enumerate(doc, start=1):
            pix = page.get_pixmap(dpi=dpi)
            img_path = out_dir / f"{stem}_p{i:04d}.png"
            pix.save(str(img_path))
            if progress_callback:
                progress_callback(f"转图片 ({i}/{total})", int(i/total*100))
        doc.close()
        return total

    # ── 7. 图片 → PDF ─────────────────────────────────

    @staticmethod
    def from_images(
        image_paths: List[Path],
        output_path: Path,
        progress_callback: Optional[Callable[[str, int], None]] = None,
    ) -> None:
        """将多张图片合并为一个 PDF。"""
        import fitz
        from PIL import Image as PILImage

        doc = fitz.open()
        total = len(image_paths)
        for i, p in enumerate(image_paths):
            check_input(p)
            # 用 Pillow 获取图片尺寸
            with PILImage.open(p) as img:
                w, h = img.size
            # 创建对应尺寸的 PDF 页面，插入图片
            page = doc.new_page(width=w, height=h)
            page.insert_image(page.rect, filename=str(p))
            if progress_callback:
                progress_callback(f"加载图片 ({i+1}/{total}): {p.name}", int((i+1)/total*100))

        doc.save(output_path)
        doc.close()

    # ── 8. 压缩 ───────────────────────────────────────

    @staticmethod
    def compress(
        input_path: Path,
        output_path: Path,
        progress_callback: Optional[Callable[[str, int], None]] = None,
    ) -> dict:
        """压缩 PDF。返回 {before_bytes, after_bytes, ratio}。"""
        import pikepdf

        check_input(input_path)
        if progress_callback:
            progress_callback("正在压缩...", 50)

        pdf = pikepdf.open(input_path)
        pdf.save(
            output_path,
            compress_streams=True,
            object_stream_mode=pikepdf.ObjectStreamMode.generate,
        )
        pdf.close()

        before = input_path.stat().st_size
        after = output_path.stat().st_size
        ratio = (1 - after / before) * 100 if before > 0 else 0

        if progress_callback:
            progress_callback("压缩完成", 100)

        return {"before_bytes": before, "after_bytes": after, "ratio": ratio}

    # ── 9. 加水印 ─────────────────────────────────────

    @staticmethod
    def watermark(
        input_path: Path,
        watermark_path: Path,
        output_path: Path,
        progress_callback: Optional[Callable[[str, int], None]] = None,
    ) -> None:
        """给每一页叠加水印 PDF。"""
        from pypdf import PdfReader, PdfWriter

        check_input(input_path)
        check_input(watermark_path)

        reader = PdfReader(input_path)
        watermark_reader = PdfReader(watermark_path)
        watermark_page = watermark_reader.pages[0]
        writer = PdfWriter()
        total = len(reader.pages)

        for i, page in enumerate(reader.pages):
            page.merge_page(watermark_page)
            writer.add_page(page)
            if progress_callback:
                progress_callback(f"加水印 ({i+1}/{total})", int((i+1)/total*100))

        with open(output_path, "wb") as f:
            writer.write(f)

    # ── 10. 加密 ──────────────────────────────────────

    @staticmethod
    def encrypt(
        input_path: Path,
        output_path: Path,
        password: str,
        progress_callback: Optional[Callable[[str, int], None]] = None,
    ) -> None:
        """给 PDF 设置打开密码。"""
        from pypdf import PdfReader, PdfWriter

        check_input(input_path)
        if progress_callback:
            progress_callback("正在加密...", 50)

        reader = PdfReader(input_path)
        writer = PdfWriter()
        for page in reader.pages:
            writer.add_page(page)
        writer.encrypt(password)

        with open(output_path, "wb") as f:
            writer.write(f)

        if progress_callback:
            progress_callback("加密完成", 100)

    # ── 11. 解密 ──────────────────────────────────────

    @staticmethod
    def decrypt(
        input_path: Path,
        output_path: Path,
        password: str,
        progress_callback: Optional[Callable[[str, int], None]] = None,
    ) -> None:
        """解密 PDF（移除密码）。密码错误时抛出 ValueError。"""
        from pypdf import PdfReader, PdfWriter

        check_input(input_path)
        if progress_callback:
            progress_callback("正在解密...", 30)

        reader = PdfReader(input_path)
        if reader.is_encrypted:
            result = reader.decrypt(password)
            if result == 0:
                raise ValueError("密码不正确，无法解密")

        writer = PdfWriter()
        total = len(reader.pages)
        for i, page in enumerate(reader.pages):
            writer.add_page(page)
            if progress_callback:
                progress_callback(f"解密中 ({i+1}/{total})", 30 + int((i+1)/total*70))

        with open(output_path, "wb") as f:
            writer.write(f)

        if progress_callback:
            progress_callback("解密完成", 100)

    # ── 12. 旋转 ──────────────────────────────────────

    @staticmethod
    def rotate(
        input_path: Path,
        output_path: Path,
        angle: int,
        pages: Optional[List[int]] = None,
        progress_callback: Optional[Callable[[str, int], None]] = None,
    ) -> None:
        """旋转指定页面（90/180/270）。"""
        from pypdf import PdfReader, PdfWriter

        if angle not in (90, 180, 270):
            raise ValueError(f"旋转角度必须是 90/180/270，收到: {angle}")

        check_input(input_path)
        reader = PdfReader(input_path)
        writer = PdfWriter()
        total = len(reader.pages)

        for i, page in enumerate(reader.pages):
            pnum = i + 1
            if pages is None or pnum in pages:
                page.rotate(angle)
            writer.add_page(page)
            if progress_callback:
                progress_callback(f"旋转中 ({pnum}/{total})", int(pnum/total*100))

        with open(output_path, "wb") as f:
            writer.write(f)

    # ── 13. 水印（文字） ─────────────────────────────

    @staticmethod
    def text_watermark(
        input_path: Path,
        output_path: Path,
        text: str,
        font_size: int = 60,
        opacity: float = 0.3,
        rotation: float = 45,
        progress_callback: Optional[Callable[[str, int], None]] = None,
    ) -> None:
        """在 PDF 每页上添加文字水印（对角线重复）。

        rotation 会被圆整到最近的有效角度 (0/90/180/270)。
        """
        import fitz

        # PyMuPDF 只支持 0/90/180/270
        valid_angles = [0, 90, 180, 270]
        rotate = min(valid_angles, key=lambda a: abs(a - rotation))

        check_input(input_path)
        doc = fitz.open(input_path)
        total = len(doc)

        for pi in range(total):
            page = doc[pi]
            rect = page.rect
            for x_frac in (0.3, 0.6):
                for y_frac in (0.25, 0.5, 0.75):
                    x = rect.x0 + rect.width * x_frac
                    y = rect.y0 + rect.height * y_frac
                    page.insert_text(
                        fitz.Point(x, y),
                        text,
                        fontsize=font_size,
                        color=(0.7, 0.7, 0.7),
                        rotate=rotate,
                        overlay=True,
                    )
            if progress_callback:
                progress_callback(f"添加文字水印 ({pi+1}/{total})", int((pi+1)/total*100))

        doc.save(output_path, incremental=False)
        doc.close()
