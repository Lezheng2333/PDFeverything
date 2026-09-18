# PDFeverything MCP Server — AI Agent Integration Guide

This MCP server lets any AI agent (Claude Desktop, Claude Code, Cursor, etc.) discover and call PDFeverything tools directly — no Python, no dependencies, just the compiled `.exe` or `.app`.

## 🚀 Quick Setup

### Claude Desktop

Add to `~/.claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "pdfeverything": {
      "command": "python",
      "args": ["mcp/server.py"],
      "cwd": "/path/to/PDFeverything"
    }
  }
}
```

Or using the compiled exe (no Python needed):

```json
{
  "mcpServers": {
    "pdfeverything": {
      "command": "C:\\Program Files\\PDFeverything\\PDFeverything.exe",
      "args": ["--mcp"]
    }
  }
}
```

### Claude Code

Add to `.claude/settings.json` in your project:

```json
{
  "mcpServers": {
    "pdfeverything": {
      "type": "stdio",
      "command": "PDFeverything",
      "args": ["--mcp"]
    }
  }
}
```

## 🔧 Available Tools (25 tools)

The AI agent will see these tools automatically:

| Tool | What it does |
|---|---|
| `pdf_merge` | Merge several PDFs into one, in the order you list them |
| `pdf_split` | Split a PDF into single pages (or by custom ranges) |
| `pdf_info` | Metadata: page count, size, author, title, encryption status |
| `pdf_outline` | Bookmark / table-of-contents tree with target pages |
| `pdf_search` | Find text in a PDF — every match with page, position and context |
| `pdf_extract_text` | Extract all text from a PDF to a .txt file |
| `pdf_extract_images` | Extract every embedded image to a folder |
| `pdf_to_images` | Render each page to a PNG (adjustable DPI) |
| `images_to_pdf` | Combine images (PNG/JPG/GIF/…) into one PDF |
| `pdf_to_word` | Convert a PDF to Word (.docx), keeping text and tables |
| `pdf_to_ppt` | Convert a PDF to PowerPoint (.pptx), one slide per page |
| `pdf_to_excel` | Extract PDF tables into Excel sheets (.xlsx) |
| `pdf_compress` | Shrink a PDF (lossless / medium / max) |
| `pdf_watermark` | Add a text watermark with real opacity and angle |
| `pdf_encrypt` | Set an open password (AES-256) |
| `pdf_decrypt` | Remove the password from a PDF |
| `pdf_rotate` | Rotate pages 90/180/270° |
| `pdf_mixed_merge` | 🔥 The killer feature: merge mixed file types into one PDF |
| `pdf_delete_pages` | Delete pages by 1-based number or range |
| `pdf_rotate_pages` | Rotate specific pages |
| `pdf_move_pages` | Reorder pages by moving them before a target position |
| `pdf_extract_pages` | Extract pages into a new standalone PDF |
| `pdf_undo` | Undo the last page edit (history persists per file) |
| `pdf_redo` | Redo the last undone page edit |
| `pdf_history` | Show the recorded editing history for a file |

## 🧪 Test It

```bash
# Start the MCP server directly:
python mcp/server.py

# Or from compiled exe:
PDFeverything.exe --mcp

# Send a test request (type this into the running server):
{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}
```

## 📋 How AI Agents Discover the Tools

The MCP protocol works over stdin/stdout JSON-RPC:

```
AI Agent                          PDFeverything MCP Server
   │                                       │
   │── {"method":"tools/list"} ──────────► │
   │                                       │
   │◄─ {"result":{"tools":[...25 tools]}} │
   │                                       │
   │── {"method":"tools/call",            │
   │     "params":{"name":"pdf_info",      │
   │     "arguments":{"input":"doc.pdf"}}} │
   │                                       │
   │◄─ {"result":{"content":[{"text":     │
   │     "{'pages':5,'title':'Report'}"}]}}
```

No setup required — the agent calls `pdfeverything --mcp`, the server starts, and all 23 tools appear in its toolbox automatically.
