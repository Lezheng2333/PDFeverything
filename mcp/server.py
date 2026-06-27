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

import json
import sys
import subprocess
from pathlib import Path
from typing import Any

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
        "description": "Rotate pages in a PDF by 90, 180, or 270 degrees. You can rotate all pages or specific pages.",
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
                "pages": {"type": "string", "description": "Page numbers: 1,3,5 or 1-5 or all"},
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
                "source": {"type": "string", "description": "Source page numbers: 1,2"},
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
                "pages": {"type": "string", "description": "Page numbers to extract (1-based): 1,3,5 or 1-5 or all"}
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
        "description": "Show the operation history for a PDF editing session.",
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
    """Parse page range string to 0-based ordinal indices."""
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
            outputs = PdfOperator.split(Path(args["input"]), Path(args["output_dir"]))
            return json.dumps({
                "success": True,
                "pages": len(outputs),
                "output_dir": args["output_dir"]
            })

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
            result = PdfOperator.compress(Path(args["input"]), Path(args["output"]))
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
            pages = _parse_page_list(args["pages"], total)
            editor.delete_pages(pages)
            editor.save(Path(args["output"])); editor.close()
            return json.dumps({"success": True, "deleted": len(pages), "remaining": total - len(pages)})

        elif name == "pdf_rotate_pages":
            from core.page_editor import PdfPageEditor as PE
            editor = PE(Path(args["input"]))
            total = editor.page_count
            pages = _parse_page_list(args["pages"], total)
            editor.rotate_pages(pages, args["degrees"])
            editor.save(Path(args["output"])); editor.close()
            return json.dumps({"success": True, "rotated": len(pages), "degrees": args["degrees"]})

        elif name == "pdf_move_pages":
            from core.page_editor import PdfPageEditor as PE
            editor = PE(Path(args["input"]))
            total = editor.page_count
            source = _parse_page_list(args["source"], total)
            target = args["target"] - 1  # 1-based to 0-based
            editor.move_pages(source, target)
            editor.save(Path(args["output"])); editor.close()
            return json.dumps({"success": True, "moved": len(source), "to": args["target"]})

        elif name == "pdf_extract_pages":
            from core.page_editor import PdfPageEditor as PE
            editor = PE(Path(args["input"]))
            total = editor.page_count
            pages = _parse_page_list(args["pages"], total)
            editor.extract_pages(pages, Path(args["output"]))
            editor.close()
            return json.dumps({"success": True, "extracted": len(pages)})

        elif name == "pdf_undo":
            from core.page_editor import PdfPageEditor as PE
            editor = PE(Path(args["input"]))
            desc = editor.undo()
            if desc:
                editor.save(Path(args["output"]))
            editor.close()
            return json.dumps({"success": desc is not None, "undo": desc or "nothing to undo"})

        elif name == "pdf_redo":
            from core.page_editor import PdfPageEditor as PE
            editor = PE(Path(args["input"]))
            desc = editor.redo()
            if desc:
                editor.save(Path(args["output"]))
            editor.close()
            return json.dumps({"success": desc is not None, "redo": desc or "nothing to redo"})

        elif name == "pdf_history":
            from core.page_editor import PdfPageEditor as PE
            editor = PE(Path(args["input"]))
            history = editor.undo_stack_desc
            editor.close()
            return json.dumps({"success": True, "history": history})

        else:
            return json.dumps({"success": False, "error": f"Unknown tool: {name}"})

    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})
    finally:
        cleanup_temp_files()


# ── JSON-RPC / MCP transport ──────────────────────────────

def _send(msg: dict) -> None:
    """Write a JSON-RPC message to stdout."""
    sys.stdout.write(json.dumps(msg) + "\n")
    sys.stdout.flush()


def _read() -> dict | None:
    """Read a JSON-RPC message from stdin."""
    try:
        line = sys.stdin.readline()
        if not line:
            return None
        return json.loads(line.strip())
    except (json.JSONDecodeError, EOFError):
        return None


def serve() -> None:
    """Main MCP server loop — listens on stdin, responds on stdout."""
    while True:
        req = _read()
        if req is None:
            break

        msg_id = req.get("id")
        method = req.get("method", "")

        if method == "initialize":
            _send({
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {}},
                    "serverInfo": {
                        "name": "pdfeverything",
                        "version": "1.3.17"
                    }
                }
            })

        elif method == "notifications/initialized":
            pass  # no response needed for notifications

        elif method == "tools/list":
            _send({
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {"tools": TOOLS}
            })

        elif method == "tools/call":
            params = req.get("params", {})
            tool_name = params.get("name", "")
            tool_args = params.get("arguments", {})
            result_text = _run_tool(tool_name, tool_args)

            _send({
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {
                    "content": [
                        {"type": "text", "text": result_text}
                    ],
                    "isError": not json.loads(result_text).get("success", False)
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
