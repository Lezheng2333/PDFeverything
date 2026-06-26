#!/usr/bin/env python3
"""PDFeverything — entry point. GUI by default, CLI when commands are passed.

Usage:
    python main.py                          → launch GUI
    python main.py merge -i a.pdf b.pdf -o out.pdf  → CLI merge
    python main.py info -i doc.pdf          → CLI info
    python main.py -h                       → print help

The compiled .exe/.app supports the same CLI commands:
    PDFeverything.exe merge -i a.pdf b.pdf -o merged.pdf
    PDFeverything.exe info -i document.pdf
    PDFeverything.exe -h
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.resolve()))

CLI_COMMANDS = {
    "merge", "split", "extract-text", "extract-images",
    "to-images", "from-images", "compress", "watermark",
    "encrypt", "decrypt", "rotate", "info",
}

HELP_TEXT = """PDFeverything — One-stop PDF processing tool

GUI mode (default):
    PDFeverything.exe                       launch the graphical interface

CLI mode (for AI agents / headless automation):
    PDFeverything.exe <command> [options]

Commands:
    merge       -i <files...>  -o <out>      Merge PDFs into one
    split       -i <pdf>       -o <dir>       Split PDF into pages
    extract-text  -i <pdf>     -o <txt>       Extract text from PDF
    extract-images -i <pdf>    -o <dir>       Extract embedded images
    to-images   -i <pdf>       -o <dir>  [--dpi 200]  PDF pages to PNG
    from-images -i <imgs...>   -o <pdf>       Merge images into PDF
    compress    -i <pdf>       -o <pdf>       Compress PDF
    watermark   -i <pdf> -w <wmark> -o <pdf>  Add watermark
    encrypt     -i <pdf>       -o <pdf> --password <pw>   Set password
    decrypt     -i <pdf>       -o <pdf> --password <pw>   Remove password
    rotate      -i <pdf>       -o <pdf> --angle <90|180|270>  Rotate pages
    info        -i <pdf>                      Show PDF metadata

    -h, --help                                Show this help
    --version                                 Show version
    --mcp                                     Launch MCP server (for AI agents)

Examples:
    PDFeverything.exe merge -i a.pdf b.pdf c.pdf -o merged.pdf
    PDFeverything.exe info -i document.pdf
    PDFeverything.exe --mcp                  # start AI agent tool server

Note: On first run the self-extracting executable takes a few seconds to unpack.
Subsequent runs in the same session are instant.
"""


def launch_mcp():
    """Launch the MCP server for AI agent integration."""
    from mcp.server import serve
    serve()


def launch_gui():
    from PyQt6.QtWidgets import QApplication
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setOrganizationName("PDFeverything")
    app.setApplicationName("PDFeverything")
    from gui.main_window import MainWindow
    w = MainWindow()
    w.show()
    sys.exit(app.exec())


def main():
    if len(sys.argv) > 1 and sys.argv[1] in ("-h", "--help"):
        print(HELP_TEXT)
        return
    if len(sys.argv) > 1 and sys.argv[1] in ("-v", "--version"):
        print("PDFeverything v1.1.0")
        return
    if len(sys.argv) > 1 and sys.argv[1] == "--mcp":
        launch_mcp()
        return
    if len(sys.argv) > 1 and sys.argv[1] in CLI_COMMANDS:
        from pdf_tool import main as cli_main
        cli_main()
        return
    if len(sys.argv) > 1 and sys.argv[1] == "--cli":
        sys.argv.pop(1)
        if len(sys.argv) <= 1:
            print("Usage: PDFeverything.exe --cli <command> [options]")
            print("       PDFeverything.exe -h  for full help")
            sys.exit(1)
        from pdf_tool import main as cli_main
        cli_main()
        return
    launch_gui()


if __name__ == "__main__":
    main()
