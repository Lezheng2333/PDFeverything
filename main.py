#!/usr/bin/env python3
"""PDFeverything — 入口点。

用法：
    python main.py                  → 启动 GUI（默认）
    python main.py --cli ...        → 调用 CLI 模式（对应 pdf_tool.py）
    python pdf_tool.py ...          → 直接使用 CLI
"""

import sys
from pathlib import Path

# 确保项目根目录在 sys.path 中
sys.path.insert(0, str(Path(__file__).parent.resolve()))


def launch_gui():
    """启动 PyQt6 GUI。"""
    from PyQt6.QtWidgets import QApplication
    from PyQt6.QtCore import Qt

    # macOS 上用 Fusion 风格保持一致性
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setOrganizationName("PDFeverything")
    app.setApplicationName("PDFeverything")

    from gui.main_window import MainWindow
    window = MainWindow()
    window.show()

    sys.exit(app.exec())


def main():
    # 检查是否要启动 CLI 模式
    if len(sys.argv) > 1 and sys.argv[1] == "--cli":
        # 去掉 --cli 参数，将剩余参数传给 CLI
        sys.argv.pop(1)
        from pdf_tool import main as cli_main
        cli_main()
    elif len(sys.argv) > 1 and sys.argv[1] in (
        "merge", "split", "extract-text", "extract-images",
        "to-images", "from-images", "compress", "watermark",
        "encrypt", "decrypt", "rotate", "info",
    ):
        # 直接传给了 CLI 命令
        from pdf_tool import main as cli_main
        cli_main()
    else:
        # 默认启动 GUI
        launch_gui()


if __name__ == "__main__":
    main()
