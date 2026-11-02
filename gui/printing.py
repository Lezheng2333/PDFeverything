"""Print selected PDF pages through Qt's native print system."""

from PyQt6.QtCore import QRectF
from PyQt6.QtGui import QImage, QPainter


def print_pages(doc, pages, printer):
    # Preserve the caller's order while deduplicating; the UI passes pages in
    # document order, and callers that intentionally choose an order keep it.
    pages = list(dict.fromkeys(p for p in pages if 0 <= p < len(doc)))
    if not pages:
        raise ValueError("No pages selected")
    painter = QPainter()
    if not painter.begin(printer):
        raise RuntimeError("Could not start the print job")
    try:
        for index, pno in enumerate(pages):
            if index and not printer.newPage():
                raise RuntimeError("Could not advance the printer")
            pix = doc[pno].get_pixmap(dpi=min(300, max(72, printer.resolution())), alpha=False)
            img = QImage(pix.samples, pix.width, pix.height, pix.stride,
                         QImage.Format.Format_RGB888).copy()
            area = QRectF(painter.viewport())
            scale = min(area.width() / img.width(), area.height() / img.height())
            width, height = img.width() * scale, img.height() * scale
            target = QRectF(area.center().x() - width / 2,
                            area.center().y() - height / 2, width, height)
            painter.drawImage(target, img)
    finally:
        painter.end()
