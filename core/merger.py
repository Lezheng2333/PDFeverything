"""混合文件合并流水线 — 核心功能：将不同类型的文件统一转换为 PDF 后合并。"""

from pathlib import Path
from typing import Callable, Dict, List, Optional

from .converters import ConverterRegistry
from .pdf_ops import PdfOperator
from .utils import cleanup_temp_files, get_file_category, temp_dir, temp_pdf_path


def merge_mixed_files(
    file_paths: List[Path],
    output_path: Path,
    progress_callback: Optional[Callable[[str, int], None]] = None,
) -> Dict:
    """
    将混合类型的文件全部转换为 PDF 然后合并为一个 PDF。

    参数：
        file_paths: 输入文件路径列表（保持顺序）
        output_path: 输出 PDF 路径
        progress_callback: 进度回调 (msg, pct 0-100)

    返回：
        {
            "success": bool,
            "total_files": int,
            "converted": int,
            "failed": [{"path": str, "reason": str}, ...],
            "output": str,
        }
    """
    import shutil

    total = len(file_paths)
    if total == 0:
        raise ValueError("没有选择任何文件")

    failed = []
    temp_pdfs: List[Path] = []
    tmp_dir = temp_dir("pdf_merge")
    temp_dir_path = tmp_dir  # 保留引用用于清理

    try:
        # 阶段 1：逐个转换（占 0-80% 进度）
        for i, fp in enumerate(file_paths):
            ext = fp.suffix.lstrip(".").lower()
            converter = ConverterRegistry.get(ext)

            if converter is None:
                failed.append({"path": str(fp), "reason": f"不支持的文件格式: .{ext}"})
                continue

            try:
                stem = fp.stem
                # 编号保序
                out = tmp_dir / f"{i+1:04d}_{stem}.pdf"
                result = converter.convert(fp, tmp_dir, progress_callback=None)
                # 如果 converter 生成的文件名不是我们预期的，重命名
                if result != out and result.exists():
                    shutil.move(str(result), str(out))
                temp_pdfs.append(out)
                if progress_callback:
                    pct = int((i + 1) / total * 80)
                    progress_callback(f"转换中 ({i+1}/{total}): {fp.name}", pct)
            except Exception as e:
                failed.append({"path": str(fp), "reason": str(e)})
                if progress_callback:
                    pct = int((i + 1) / total * 80)
                    progress_callback(f"跳过 ({i+1}/{total}): {fp.name} — {e}", pct)

        if not temp_pdfs:
            raise RuntimeError("没有文件可以合并（所有文件转换均失败）")

        # 阶段 2：合并（占 80-100% 进度）
        if progress_callback:
            progress_callback("正在合并 PDF...", 85)

        PdfOperator.merge(
            temp_pdfs, output_path,
            progress_callback=lambda msg, pct: (
                progress_callback(f"合并中: {msg}", 80 + int(pct * 0.2))
                if progress_callback else None
            ),
        )

        if progress_callback:
            progress_callback("完成!", 100)

        return {
            "success": True,
            "total_files": total,
            "converted": len(temp_pdfs),
            "failed": failed,
            "output": str(output_path),
        }

    finally:
        # 清理临时文件
        cleanup_temp_files()
