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

## 🔧 Available Tools (13 tools)

The AI agent will see these tools automatically:

| Tool | What it does |
|---|---|
| `pdf_merge` | Merge multiple PDFs into one |
| `pdf_split` | Split PDF into separate pages |
| `pdf_info` | Get PDF metadata (pages, size, author, etc.) |
| `pdf_extract_text` | Extract all text from a PDF |
| `pdf_extract_images` | Extract embedded images from a PDF |
| `pdf_to_images` | Convert PDF pages to PNG images |
| `images_to_pdf` | Combine images into a PDF |
| `pdf_compress` | Reduce PDF file size |
| `pdf_watermark` | Add text watermark to every page |
| `pdf_encrypt` | Set password on a PDF |
| `pdf_decrypt` | Remove password from a PDF |
| `pdf_rotate` | Rotate pages 90/180/270 degrees |
| `pdf_mixed_merge` | 🔥 Merge mixed files (PDF+Word+PPT+Excel+images+text) into one PDF |

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
   │◄─ {"result":{"tools":[...13 tools]}} │
   │                                       │
   │── {"method":"tools/call",            │
   │     "params":{"name":"pdf_info",      │
   │     "arguments":{"input":"doc.pdf"}}} │
   │                                       │
   │◄─ {"result":{"content":[{"text":     │
   │     "{'pages':5,'title':'Report'}"}]}}
```

No setup required — the agent calls `pdfeverything --mcp`, the server starts, and all 13 tools appear in its toolbox automatically.
