#!/usr/bin/env python3
"""
PDFeverything MCP Server — lets AI agents (Claude, Cursor, etc.) discover and
call PDFeverything CLI tools natively via Model Context Protocol.

Usage:
    python mcp/server.py          # run as standalone MCP server
    PDFeverything --mcp           # same, from compiled exe

Connect from Claude Desktop / Claude Code config:
    {
      "mcpServers": {
        "pdfeverything": {
          "command": "python",
          "args": ["mcp/server.py"],
          "cwd": "/path/to/PDFeverything"
        }
      }
    }
    // Or with compiled exe:
    {
      "mcpServers": {
        "pdfeverything": {
          "command": "PDFeverything.exe",
          "args": ["--mcp"]
        }
      }
    }
"""

import contextlib
import json
import os
import sys
from pathlib import Path

# PyMuPDF prints a one-line recommendation to stdout the first time table
# detection runs. On a stdio JSON-RPC channel that plain-text line corrupts the
# stream and the client loses sync with the server, so silence it before any
# core module gets a chance to call into MuPDF.
os.environ.setdefault("PYMUPDF_SUGGEST_LAYOUT_ANALYZER", "0")
try:  # pragma: no cover - depends on the installed PyMuPDF build
    import pymupdf

    pymupdf.no_recommend_layout()
except Exception:
    try:
        import fitz

        fitz.no_recommend_layout()
    except Exception:
        pass

SERVER_VERSION = "1.9.0"

# ── Tool definitions (OpenAI-compatible JSON schemas) ──────

TOOLS = [
    {
        "name": "pdf_merge",
        "description": "Merge multiple PDF files into a single PDF. Files are combined in the order you specify.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "input_files": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Absolute paths to the PDF files to merge, in order"
                },
                "output": {
                    "type": "string",
                    "description": "Absolute path for the output merged PDF file"
                }
            },
            "minItems": 1,
            "required": ["input_files", "output"]
        }
    },
    {
        "name": "pdf_split",
        "description": "Split a PDF into individual pages or by custom page ranges. Each range becomes a separate PDF file in the output directory.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "input": {
                    "type": "string",
                    "description": "Absolute path to the input PDF file"
                },
                "output_dir": {
                    "type": "string",
                    "description": "Absolute path to the directory where split PDFs will be saved"
                },
                "page_ranges": {
                    "type": "array",
                    "items": {
                        "type": "array",
                        "items": {"type": "integer"}
                    },
                    "description": "Optional 1-based inclusive ranges, e.g. [[1,5],[6,10]]. Omit to split every page into its own file."
                }
            },
            "required": ["input", "output_dir"]
        }
    },
    {
        "name": "pdf_info",
        "description": "Get metadata about a PDF file: page count, encryption status, title, author, file size, etc.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "input": {
                    "type": "string",
                    "description": "Absolute path to the PDF file to inspect"
                }
            },
            "required": ["input"]
        }
    },
    {
        "name": "pdf_add_page_numbers",
        "description": "Stamp page numbers, headers or footers onto a PDF. The template supports {n} (current number), {total} (page count) and {page} (original page number), so you can write things like 'Page {n} of {total}'.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "input": {"type": "string", "description": "Absolute path to the input PDF"},
                "output": {"type": "string", "description": "Absolute path for the output PDF"},
                "position": {
                    "type": "string",
                    "enum": ["bottom-center", "bottom-left", "bottom-right",
                             "top-center", "top-left", "top-right"],
                    "description": "Where on the page to stamp (default: bottom-center)",
                    "default": "bottom-center"
                },
                "template": {
                    "type": "string",
                    "description": "Text template, e.g. '{n}' or 'Page {n} of {total}'",
                    "default": "{n}"
                },
                "start_number": {"type": "integer", "description": "First number (default 1)", "default": 1},
                "font_size": {"type": "integer", "description": "Font size in points (default 10)", "default": 10},
                "pages": {"type": "string",
                          "description": "Page range: 'all', '3' or '1-5' or '1-3,7,9-12' (default: all)"}
            },
            "required": ["input", "output"]
        }
    },
    {
        "name": "pdf_set_metadata",
        "description": "Set PDF document properties (title, author, subject, keywords, creator, producer). Only the fields you pass are changed.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "input": {"type": "string", "description": "Absolute path to the input PDF"},
                "output": {"type": "string", "description": "Absolute path for the output PDF"},
                "title": {"type": "string"},
                "author": {"type": "string"},
                "subject": {"type": "string"},
                "keywords": {"type": "string"},
                "creator": {"type": "string"},
                "producer": {"type": "string"}
            },
            "required": ["input", "output"]
        }
    },
    {
        "name": "pdf_nup",
        "description": "Impose several PDF pages onto one sheet (N-up) for paper-saving printing — 2, 4, 6, 8, 9 or 16 pages per sheet.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "input": {"type": "string", "description": "Absolute path to the input PDF"},
                "output": {"type": "string", "description": "Absolute path for the output PDF"},
                "per_sheet": {
                    "type": "integer",
                    "enum": [2, 4, 6, 8, 9, 16],
                    "description": "Pages per sheet (default 2)",
                    "default": 2
                },
                "paper": {
                    "type": "string",
                    "enum": ["a4", "a3", "letter"],
                    "description": "Sheet size (default a4)",
                    "default": "a4"
                }
            },
            "required": ["input", "output"]
        }
    },
    {
        "name": "pdf_insert_pages",
        "description": "Insert every page of one PDF into another at a given position (or append at the end). Links and annotations are preserved.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "input": {"type": "string", "description": "Absolute path to the target PDF"},
                "source": {"type": "string", "description": "Absolute path to the PDF whose pages get inserted"},
                "output": {"type": "string", "description": "Absolute path for the output PDF"},
                "at": {
                    "type": "integer",
                    "description": "1-based insert position; omit to append at the end"
                }
            },
            "required": ["input", "source", "output"]
        }
    },
    {
        "name": "pdf_search",
        "description": "Search for text inside a PDF and return every match with its page number, position and surrounding context. Useful for locating a clause, invoice number or keyword before extracting pages.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "input": {
                    "type": "string",
                    "description": "Absolute path to the PDF file to search"
                },
                "query": {
                    "type": "string",
                    "description": "Text to look for (case-insensitive by default)"
                },
                "case_sensitive": {
                    "type": "boolean",
                    "description": "Match case exactly (default: false)",
                    "default": False
                },
                "whole_word": {
                    "type": "boolean",
                    "description": "Only match whole words (default: false)",
                    "default": False
                },
                "pages": {
                    "type": "string",
                    "description": "Limit the search to a page range. Page range: 'all', '3' or '1-5' or '1-3,7,9-12' (default: all pages)"
                },
                "max_hits": {
                    "type": "integer",
                    "description": "Stop after this many matches (default: 500)",
                    "default": 500
                }
            },
            "required": ["input", "query"]
        }
    },
    {
        "name": "pdf_outline",
        "description": "Return the bookmark/table-of-contents tree of a PDF with the page each entry points to.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "input": {
                    "type": "string",
                    "description": "Absolute path to the PDF file"
                }
            },
            "required": ["input"]
        }
    },
    {
        "name": "pdf_extract_text",
        "description": "Extract all text content from a PDF file and save to a text file. Returns the full text content.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "input": {
                    "type": "string",
                    "description": "Absolute path to the input PDF file"
                },
                "output": {
                    "type": "string",
                    "description": "Absolute path for the output text file"
                }
            },
            "required": ["input", "output"]
        }
    },
    {
        "name": "pdf_extract_images",
        "description": "Extract all embedded images from a PDF file and save them to a directory.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "input": {
                    "type": "string",
                    "description": "Absolute path to the input PDF file"
                },
                "output_dir": {
                    "type": "string",
                    "description": "Absolute path to the directory where images will be saved"
                }
            },
            "required": ["input", "output_dir"]
        }
    },
    {
        "name": "pdf_to_images",
        "description": "Convert each page of a PDF to a PNG image file. All images are saved to the output directory.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "input": {
                    "type": "string",
                    "description": "Absolute path to the input PDF file"
                },
                "output_dir": {
                    "type": "string",
                    "description": "Absolute path to the directory where PNG images will be saved"
                },
                "dpi": {
                    "type": "integer",
                    "description": "Image resolution in DPI (default: 200)",
                    "default": 200
                }
            },
            "required": ["input", "output_dir"]
        }
    },
    {
        "name": "images_to_pdf",
        "description": "Combine multiple image files (PNG, JPG, GIF, etc.) into a single PDF. Each image becomes one page.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "input_files": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Absolute paths to image files, in order"
                },
                "output": {
                    "type": "string",
                    "description": "Absolute path for the output PDF file"
                }
            },
            "required": ["input_files", "output"]
        }
    },
    {
        "name": "pdf_compress",
        "description": "Compress a PDF file to reduce its size. Returns the before and after sizes and compression ratio.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "input": {
                    "type": "string",
                    "description": "Absolute path to the input PDF file"
                },
                "output": {
                    "type": "string",
                    "description": "Absolute path for the compressed PDF file"
                },
                "mode": {
                    "type": "string",
                    "enum": ["lossless", "medium", "max"],
                    "description": "lossless rewrites object streams only (no quality change); medium re-encodes images at 150 DPI / quality 75; max uses 96 DPI / quality 45 (default: lossless)",
                    "default": "lossless"
                }
            },
            "required": ["input", "output"]
        }
    },
    {
        "name": "pdf_watermark",
        "description": "Add a text watermark (like 'CONFIDENTIAL' or 'DRAFT') to every page of a PDF. The watermark appears diagonally across each page.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "input": {
                    "type": "string",
                    "description": "Absolute path to the input PDF file"
                },
                "output": {
                    "type": "string",
                    "description": "Absolute path for the watermarked PDF file"
                },
                "text": {
                    "type": "string",
                    "description": "Watermark text to stamp on every page (e.g. 'CONFIDENTIAL')"
                },
                "font_size": {
                    "type": "integer",
                    "description": "Font size for the watermark text (default: 60)",
                    "default": 60
                },
                "opacity": {
                    "type": "number",
                    "description": "Opacity of the watermark from 0.0 to 1.0 (default: 0.3)",
                    "default": 0.3
                },
                "rotation": {
                    "type": "integer",
                    "description": "Rotation angle in degrees (default: 45). Will be rounded to 0/90/180/270.",
                    "default": 45
                }
            },
            "required": ["input", "output", "text"]
        }
    },
    {
        "name": "pdf_encrypt",
        "description": "Set an open password on a PDF file. The file cannot be opened without the password.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "input": {
                    "type": "string",
                    "description": "Absolute path to the input PDF file"
                },
                "output": {
                    "type": "string",
                    "description": "Absolute path for the encrypted PDF file"
                },
                "password": {
                    "type": "string",
                    "description": "Password to protect the PDF with"
                }
            },
            "required": ["input", "output", "password"]
        }
    },
    {
        "name": "pdf_decrypt",
        "description": "Remove the password protection from an encrypted PDF file.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "input": {
                    "type": "string",
                    "description": "Absolute path to the encrypted PDF file"
                },
                "output": {
                    "type": "string",
                    "description": "Absolute path for the decrypted PDF file"
                },
                "password": {
                    "type": "string",
                    "description": "The password to unlock the PDF"
                }
            },
            "required": ["input", "output", "password"]
        }
    },
    {
        "name": "pdf_rotate",
        "description": "Rotate pages in a PDF by 90, 180, or 270 degrees. Omit `pages` to rotate all pages; otherwise pass a list of 1-based page numbers.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "input": {
                    "type": "string",
                    "description": "Absolute path to the input PDF file"
                },
                "output": {
                    "type": "string",
                    "description": "Absolute path for the rotated PDF file"
                },
                "angle": {
                    "type": "integer",
                    "description": "Rotation angle: 90, 180, or 270 degrees",
                    "enum": [90, 180, 270]
                },
                "pages": {
                    "type": "array",
                    "items": {"type": "integer"},
                    "description": "Specific page numbers to rotate (1-based). Omit to rotate all pages."
                }
            },
            "required": ["input", "output", "angle"]
        }
    },
    {
        "name": "pdf_mixed_merge",
        "description": "THE KILLER FEATURE: Merge mixed file types (PDFs, Word .docx, PowerPoint .pptx, Excel .xlsx, images, text files) into a single unified PDF. Each file is automatically converted before merging. File order is preserved.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "input_files": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Absolute paths to files in order. Supports: .pdf, .docx, .doc, .pptx, .ppt, .xlsx, .xls, .png, .jpg, .jpeg, .gif, .bmp, .tiff, .webp, .txt, .md, .json, .xml, .html, .csv"
                },
                "output": {
                    "type": "string",
                    "description": "Absolute path for the output unified PDF file"
                }
            },
            "required": ["input_files", "output"]
        }
    },
    {
        "name": "pdf_to_word",
        "description": "Convert a PDF file to Microsoft Word (.docx) format. Preserves text structure, headings, and tables from the PDF.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "input": {
                    "type": "string",
                    "description": "Absolute path to the input PDF file"
                },
                "output": {
                    "type": "string",
                    "description": "Absolute path for the output .docx file"
                }
            },
            "required": ["input", "output"]
        }
    },
    {
        "name": "pdf_to_ppt",
        "description": "Convert a PDF file to Microsoft PowerPoint (.pptx) format. Each PDF page becomes one slide with the page rendered as a full-slide image.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "input": {
                    "type": "string",
                    "description": "Absolute path to the input PDF file"
                },
                "output": {
                    "type": "string",
                    "description": "Absolute path for the output .pptx file"
                },
                "dpi": {
                    "type": "integer",
                    "description": "Image resolution in DPI for rendering pages (default: 200)",
                    "default": 200
                }
            },
            "required": ["input", "output"]
        }
    },
    {
        "name": "pdf_to_excel",
        "description": "Extract tables from a PDF into Microsoft Excel (.xlsx) format. Each table found becomes a separate worksheet. Falls back to extracted text if no tables are detected.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "input": {
                    "type": "string",
                    "description": "Absolute path to the input PDF file"
                },
                "output": {
                    "type": "string",
                    "description": "Absolute path for the output .xlsx file"
                }
            },
            "required": ["input", "output"]
        }
    },
    {
        "name": "pdf_delete_pages",
        "description": "Delete specific pages from a PDF by page number (1-based). Supports comma-separated, ranges (1-5), or 'all'.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "input": {"type": "string", "description": "Absolute path to the input PDF file"},
                "output": {"type": "string", "description": "Absolute path for the output PDF file"},
                "pages": {"type": "string", "description": "Page numbers to delete (1-based): 1,3,5 or 1-5 or all"}
            },
            "required": ["input", "output", "pages"]
        }
    },
    {
        "name": "pdf_rotate_pages",
        "description": "Rotate specific pages in a PDF by 90, 180, or 270 degrees (1-based page numbers).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "input": {"type": "string", "description": "Absolute path to the input PDF file"},
                "output": {"type": "string", "description": "Absolute path for the output PDF file"},
                "pages": {"type": "string",
                          "description": "Page range: 'all', '3' or '1-5' or '1-3,7,9-12'"},
                "degrees": {"type": "integer", "enum": [90, 180, 270]}
            },
            "required": ["input", "output", "pages", "degrees"]
        }
    },
    {
        "name": "pdf_move_pages",
        "description": "Reorder pages by moving source pages to before a target position (1-based).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "input": {"type": "string", "description": "Absolute path to the input PDF file"},
                "output": {"type": "string", "description": "Absolute path for the output PDF file"},
                "source": {"type": "string",
                            "description": "Source pages to move. Page range: 'all', '3' or '1-5' or '1-3,7,9-12'"},
                "target": {"type": "integer", "description": "Target position (1-based, insert before this page)"}
            },
            "required": ["input", "output", "source", "target"]
        }
    },
    {
        "name": "pdf_extract_pages",
        "description": "Extract specific pages from a PDF into a new standalone PDF file.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "input": {"type": "string", "description": "Absolute path to the input PDF file"},
                "output": {"type": "string", "description": "Absolute path for the extracted PDF file"},
                "pages": {"type": "string",
                          "description": "Pages to keep. Page range: 'all', '3' or '1-5' or '1-3,7,9-12'"}
            },
            "required": ["input", "output", "pages"]
        }
    },
    {
        "name": "pdf_undo",
        "description": "Undo the last page editing operation (delete, rotate, move) on a PDF.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "input": {"type": "string", "description": "Absolute path to the input PDF file"},
                "output": {"type": "string", "description": "Absolute path for the output PDF file"}
            },
            "required": ["input", "output"]
        }
    },
    {
        "name": "pdf_redo",
        "description": "Redo the last undone page editing operation on a PDF.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "input": {"type": "string", "description": "Absolute path to the input PDF file"},
                "output": {"type": "string", "description": "Absolute path for the output PDF file"}
            },
            "required": ["input", "output"]
        }
    },
    {
        "name": "pdf_history",
        "description": "Show the persisted page-editing history (undo/redo states) recorded for this document, with the current cursor position.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "input": {"type": "string", "description": "Absolute path to the input PDF file"}
            },
            "required": ["input"]
        }
    },
]


# ── Helpers ─────────────────────────────────────────

def _parse_page_list(pages_str: str, total: int) -> list[int]:
    """Parse a page-range string to 0-based ordinals, using the shared parser.

    This used to be a hand-rolled splitter that accepted only "1,3" and "1-5"
    and raised a bare ValueError on anything else — so a range the CLI understood
    ("1–5", "1，3", "3-1", "1..5") silently failed or crashed on the MCP channel.
    All three channels now share one grammar (core.utils.parse_page_ranges)."""
    from core.utils import parse_page_ranges

    return parse_page_ranges(pages_str, total=total, one_based=True)


def _require_pages(pages: list, total: int, what: str = "pages") -> list:
    """Reject an empty selection instead of silently doing nothing."""
    if not pages:
        raise ValueError(f"{what} 没有匹配任何页面 (文档共 {total} 页)")
    return pages


# ── Command handlers — delegate to core.PdfOperator ────────

def _run_tool(name: str, args: dict) -> str:
    """Execute a tool and return the result as a JSON string."""
    # Add project root to path so we can import core modules
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from core.pdf_ops import PdfOperator
    from core.merger import merge_mixed_files
    from core.utils import format_bytes, cleanup_temp_files

    try:
        if name == "pdf_merge":
            paths = [Path(p) for p in args["input_files"]]
            PdfOperator.merge(paths, Path(args["output"]))
            return json.dumps({
                "success": True,
                "merged_files": len(paths),
                "output": args["output"]
            })

        elif name == "pdf_split":
            ranges = args.get("page_ranges")
            page_ranges = None
            if ranges:
                page_ranges = [(int(r[0]), int(r[1])) for r in ranges if len(r) >= 2]
            outputs = PdfOperator.split(Path(args["input"]), Path(args["output_dir"]),
                                        page_ranges)
            return json.dumps({
                "success": True,
                "pages": len(outputs),
                "output_dir": args["output_dir"]
            })

        elif name == "pdf_add_page_numbers":
            from core.utils import parse_page_ranges

            pages = (parse_page_ranges(args["pages"], one_based=True)
                     if args.get("pages") else None)
            count = PdfOperator.add_page_numbers(
                Path(args["input"]), Path(args["output"]),
                position=args.get("position", "bottom-center"),
                start_number=int(args.get("start_number", 1) or 1),
                font_size=int(args.get("font_size", 10) or 10),
                template=args.get("template", "{n}") or "{n}",
                pages=pages)
            return json.dumps({"success": True, "output": args["output"],
                               "pages_stamped": count}, ensure_ascii=False)

        elif name == "pdf_set_metadata":
            fields = {k: args[k] for k in PdfOperator.METADATA_FIELDS if args.get(k) is not None}
            if not fields:
                return json.dumps({"success": False,
                                   "error": "no metadata fields provided"})
            result = PdfOperator.set_metadata(Path(args["input"]), Path(args["output"]),
                                              fields)
            return json.dumps({"success": True, "output": args["output"],
                               "metadata": result}, ensure_ascii=False)

        elif name == "pdf_nup":
            sheets = PdfOperator.nup(Path(args["input"]), Path(args["output"]),
                                     per_sheet=int(args.get("per_sheet", 2) or 2),
                                     paper=args.get("paper", "a4") or "a4")
            return json.dumps({"success": True, "output": args["output"],
                               "sheets": sheets}, ensure_ascii=False)

        elif name == "pdf_insert_pages":
            at = args.get("at")
            inserted = PdfOperator.insert_pages(
                Path(args["input"]), Path(args["source"]), Path(args["output"]),
                at=None if at is None else int(at) - 1)
            return json.dumps({"success": True, "output": args["output"],
                               "inserted_pages": inserted}, ensure_ascii=False)

        elif name == "pdf_search":
            from core.search import search_pdf

            spec = args.get("pages")
            pages = None
            if spec:
                from core.utils import parse_page_ranges
                pages = parse_page_ranges(spec, one_based=True)
            result = search_pdf(
                Path(args["input"]), args["query"],
                case_sensitive=bool(args.get("case_sensitive", False)),
                whole_word=bool(args.get("whole_word", False)),
                pages=pages,
                max_hits=int(args.get("max_hits", 500) or 500),
            )
            return json.dumps(result.as_dict(), ensure_ascii=False)

        elif name == "pdf_outline":
            from core.search import get_outline

            entries = get_outline(Path(args["input"]))
            return json.dumps({
                "success": True,
                "count": len(entries),
                "outline": [e.as_dict() for e in entries],
            }, ensure_ascii=False)

        elif name == "pdf_info":
            info = PdfOperator.get_info(Path(args["input"]))
            info["size_human"] = format_bytes(info["size_bytes"])
            info["success"] = True
            return json.dumps(info, ensure_ascii=False)

        elif name == "pdf_extract_text":
            text = PdfOperator.extract_text(Path(args["input"]), Path(args["output"]))
            return json.dumps({
                "success": True,
                "output": args["output"],
                "characters": len(text),
                "preview": text[:500]
            }, ensure_ascii=False)

        elif name == "pdf_extract_images":
            count = PdfOperator.extract_images(Path(args["input"]), Path(args["output_dir"]))
            return json.dumps({
                "success": True,
                "images_extracted": count,
                "output_dir": args["output_dir"]
            })

        elif name == "pdf_to_images":
            dpi = args.get("dpi", 200)
            count = PdfOperator.to_images(Path(args["input"]), Path(args["output_dir"]), dpi=dpi)
            return json.dumps({
                "success": True,
                "pages_converted": count,
                "output_dir": args["output_dir"],
                "dpi": dpi
            })

        elif name == "images_to_pdf":
            paths = [Path(p) for p in args["input_files"]]
            PdfOperator.from_images(paths, Path(args["output"]))
            return json.dumps({
                "success": True,
                "images_count": len(paths),
                "output": args["output"]
            })

        elif name == "pdf_compress":
            result = PdfOperator.compress(Path(args["input"]), Path(args["output"]),
                                          mode=args.get("mode", "lossless") or "lossless")
            result["success"] = True
            result["before_human"] = format_bytes(result["before_bytes"])
            result["after_human"] = format_bytes(result["after_bytes"])
            return json.dumps(result)

        elif name == "pdf_watermark":
            text = args["text"]
            font_size = args.get("font_size", 60)
            opacity = args.get("opacity", 0.3)
            rotation = args.get("rotation", 45)
            PdfOperator.text_watermark(
                Path(args["input"]), Path(args["output"]),
                text, font_size, opacity, rotation
            )
            return json.dumps({
                "success": True,
                "watermark_text": text,
                "output": args["output"]
            })

        elif name == "pdf_encrypt":
            PdfOperator.encrypt(Path(args["input"]), Path(args["output"]), args["password"])
            return json.dumps({
                "success": True,
                "output": args["output"]
            })

        elif name == "pdf_decrypt":
            PdfOperator.decrypt(Path(args["input"]), Path(args["output"]), args["password"])
            return json.dumps({
                "success": True,
                "output": args["output"]
            })

        elif name == "pdf_rotate":
            angle = args["angle"]
            pages = args.get("pages", None)
            PdfOperator.rotate(Path(args["input"]), Path(args["output"]), angle, pages)
            return json.dumps({
                "success": True,
                "angle": angle,
                "output": args["output"]
            })


        elif name == "pdf_to_word":
            pages = PdfOperator.to_word(Path(args["input"]), Path(args["output"]))
            return json.dumps({
                "success": True,
                "pages": pages,
                "output": args["output"]
            })

        elif name == "pdf_to_ppt":
            dpi = args.get("dpi", 200)
            pages = PdfOperator.to_ppt(Path(args["input"]), Path(args["output"]), dpi=dpi)
            return json.dumps({
                "success": True,
                "pages": pages,
                "output": args["output"]
            })

        elif name == "pdf_to_excel":
            sheets = PdfOperator.to_excel(Path(args["input"]), Path(args["output"]))
            return json.dumps({
                "success": True,
                "sheets": sheets,
                "output": args["output"]
            })
        elif name == "pdf_mixed_merge":
            paths = [Path(p) for p in args["input_files"]]
            result = merge_mixed_files(paths, Path(args["output"]))
            return json.dumps(result, ensure_ascii=False)

        elif name == "pdf_delete_pages":
            from core.page_editor import PdfPageEditor as PE
            editor = PE(Path(args["input"]))
            total = editor.page_count
            pages = _require_pages(_parse_page_list(args["pages"], total), total)
            if len(pages) >= total:
                editor.close()
                return json.dumps({"success": False,
                                   "error": "不能删除全部页面"})
            editor.delete_pages(pages)
            editor.save(Path(args["output"])); editor.close()
            return json.dumps({"success": True, "deleted": len(pages), "remaining": total - len(pages)})

        elif name == "pdf_rotate_pages":
            from core.page_editor import PdfPageEditor as PE
            editor = PE(Path(args["input"]))
            total = editor.page_count
            pages = _require_pages(_parse_page_list(args["pages"], total), total)
            editor.rotate_pages(pages, args["degrees"])
            editor.save(Path(args["output"])); editor.close()
            return json.dumps({"success": True, "rotated": len(pages), "degrees": args["degrees"]})

        elif name == "pdf_move_pages":
            from core.page_editor import PdfPageEditor as PE
            editor = PE(Path(args["input"]))
            total = editor.page_count
            source = _require_pages(_parse_page_list(args["source"], total), total, "source")
            target = args["target"] - 1  # 1-based to 0-based
            editor.move_pages(source, target)
            editor.save(Path(args["output"])); editor.close()
            return json.dumps({"success": True, "moved": len(source), "to": args["target"]})

        elif name == "pdf_extract_pages":
            from core.page_editor import PdfPageEditor as PE
            editor = PE(Path(args["input"]))
            total = editor.page_count
            pages = _require_pages(_parse_page_list(args["pages"], total), total)
            editor.extract_pages(pages, Path(args["output"]))
            editor.close()
            return json.dumps({"success": True, "extracted": len(pages)})

        elif name == "pdf_undo":
            from core.page_editor import PdfPageEditor as PE
            editor = PE(Path(args["input"]))
            editor.load_journal()
            desc = editor.undo()
            if desc:
                editor.save(Path(args["output"]))
            editor.close()
            return json.dumps({"success": desc is not None, "undo": desc or "nothing to undo"})

        elif name == "pdf_redo":
            from core.page_editor import PdfPageEditor as PE
            editor = PE(Path(args["input"]))
            editor.load_journal()
            desc = editor.redo()
            if desc:
                editor.save(Path(args["output"]))
            editor.close()
            return json.dumps({"success": desc is not None, "redo": desc or "nothing to redo"})

        elif name == "pdf_history":
            from core.page_editor import PdfPageEditor as PE
            editor = PE(Path(args["input"]))
            editor.load_journal()   # same source as the CLI: the persisted journal
            history = [s["desc"] for s in editor.history]
            cursor = editor.history_cursor
            editor.close()
            return json.dumps({"success": True, "history": history,
                               "cursor": cursor, "count": len(history)},
                              ensure_ascii=False)

        else:
            return json.dumps({"success": False, "error": f"Unknown tool: {name}"})

    except Exception as e:
        return json.dumps({"success": False, "error": str(e) or type(e).__name__})
    finally:
        cleanup_temp_files()


# ── JSON-RPC / MCP transport ──────────────────────────────

def _send(msg: dict) -> None:
    """Write a JSON-RPC message to stdout."""
    sys.stdout.write(json.dumps(msg, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def _read():
    """Read one JSON-RPC line from stdin.

    Returns ("eof", None) at end of input, ("bad", None) for a malformed line and
    ("ok", message) for a decoded request. Conflating EOF with a parse error used
    to make a single blank line terminate the whole server.
    """
    try:
        line = sys.stdin.readline()
    except (EOFError, KeyboardInterrupt):
        return "eof", None
    if not line:
        return "eof", None
    stripped = line.strip()
    if not stripped:
        return "bad", None
    try:
        req = json.loads(stripped)
    except json.JSONDecodeError:
        return "bad", None
    if not isinstance(req, dict):
        return "bad", None
    return "ok", req


def serve() -> None:
    """Main MCP server loop — listens on stdin, responds on stdout."""
    while True:
        status, req = _read()
        if status == "eof":
            break
        if status == "bad":
            _send({"jsonrpc": "2.0", "id": None,
                   "error": {"code": -32700, "message": "Parse error"}})
            continue

        msg_id = req.get("id")
        method = req.get("method", "")

        # JSON-RPC 2.0: notifications (no "id") must never be answered.
        if "id" not in req and not method.startswith("notifications/"):
            continue

        if method == "initialize":
            _send({
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {}},
                    "serverInfo": {
                        "name": "pdfeverything",
                        "version": SERVER_VERSION,
                    }
                }
            })

        elif method == "notifications/initialized" or method.startswith("notifications/"):
            pass  # notifications never get a response

        elif method == "ping":
            _send({"jsonrpc": "2.0", "id": msg_id, "result": {}})

        elif method == "tools/list":
            _send({
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {"tools": TOOLS}
            })

        elif method == "tools/call":
            params = req.get("params") or {}
            tool_name = params.get("name", "")
            tool_args = params.get("arguments") or {}
            # Nothing must reach stdout except JSON-RPC frames.
            with contextlib.redirect_stdout(sys.stderr):
                result_text = _run_tool(tool_name, tool_args)
            try:
                is_error = not json.loads(result_text).get("success", False)
            except json.JSONDecodeError:
                is_error = True

            _send({
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {
                    "content": [
                        {"type": "text", "text": result_text}
                    ],
                    "isError": is_error
                }
            })

        elif method == "shutdown":
            _send({"jsonrpc": "2.0", "id": msg_id, "result": {}})
            break

        else:
            _send({
                "jsonrpc": "2.0",
                "id": msg_id,
                "error": {"code": -32601, "message": f"Unknown method: {method}"}
            })


if __name__ == "__main__":
    serve()
