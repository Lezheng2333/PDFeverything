# PDFeverything MCP Server — AI Agent Integration Guide

Current server version: **2.0.1** · **29 tools**

This MCP server lets any AI agent (Claude Desktop, Claude Code, Cursor, etc.) discover and call PDFeverything tools directly. The compiled `.exe` / `.app` needs no Python; running from source needs the project dependencies.

## 🚀 Quick Setup

### Claude Desktop

Add the server to the Claude Desktop config file, then restart the app:

- macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`
- Windows: `%APPDATA%\Claude\claude_desktop_config.json`

Compiled macOS app:

```json
{
  "mcpServers": {
    "pdfeverything": {
      "command": "/Applications/PDFeverything.app/Contents/MacOS/PDFeverything",
      "args": ["--mcp"]
    }
  }
}
```

Compiled Windows app:

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

Running from source (development):

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

### Claude Code

Add to `.mcp.json` in the project root (the file Claude Code reads for
project-scoped MCP servers):

```json
{
  "mcpServers": {
    "pdfeverything": {
      "type": "stdio",
      "command": "/Applications/PDFeverything.app/Contents/MacOS/PDFeverything",
      "args": ["--mcp"]
    }
  }
}
```

Or register it from the CLI:

```bash
claude mcp add --transport stdio pdfeverything -- \
  /Applications/PDFeverything.app/Contents/MacOS/PDFeverything --mcp
```

On Windows, use the full path to `PDFeverything.exe` in `command` (for example
`C:\\Program Files\\PDFeverything\\PDFeverything.exe`).

## 🔧 Available Tools (29 tools)

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
| `pdf_insert_pages` | Insert or append pages from another PDF |
| `pdf_nup` | Impose 2/4/6/8/9/16 pages per sheet for printing |
| `pdf_set_metadata` | Edit document properties (title, author, subject, keywords) |
| `pdf_add_page_numbers` | Stamp page numbers / headers / footers with a `{n}`/`{total}` template |
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

Page-range arguments accept `all`, `3`, `1-5`, `1-3,7,9-12`; page numbers are 1-based.
Most operations reject encrypted inputs with an actionable message; the password-related
tools (`pdf_encrypt`, `pdf_decrypt`) take an explicit password argument.

## 🧪 Test It

```bash
# Start the MCP server from source:
python mcp/server.py

# Or from the compiled app:
PDFeverything.exe --mcp
# macOS:
/Applications/PDFeverything.app/Contents/MacOS/PDFeverything --mcp

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
   │◄─ {"result":{"tools":[...29 tools]}} │
   │                                       │
   │── {"method":"tools/call",            │
   │     "params":{"name":"pdf_info",      │
   │     "arguments":{"input":"doc.pdf"}}} │
   │                                       │
   │◄─ {"result":{"content":[{"text":     │
   │     "{'pages':5,'title':'Report'}"}]}}
```

No separate install is required for the compiled app: the agent starts
`PDFeverything --mcp`, and all 29 tools appear in its toolbox automatically.

## Notes

- All MCP tools call the same `core/` implementation as the GUI and CLI.
- stdout is reserved for JSON-RPC; diagnostics go to stderr, so keep ad-hoc
  `print()` calls out of the server path.
- The server reports its version in the `initialize` response (`2.0.1`).
