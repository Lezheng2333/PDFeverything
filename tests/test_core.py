"""Non-GUI regression suite — core layer, CLI wiring and i18n invariants.

Run:  .venv/bin/python tests/test_core.py
Exit code 0 = all green.  No Qt, no display required.
"""

import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

import fitz  # noqa: E402

from core.pdf_ops import PdfOperator  # noqa: E402
from core.utils import (  # noqa: E402
    format_bytes,
    format_page_ranges,
    get_file_category,
    parse_page_ranges,
)

RESULTS = []


def check(name, condition, detail=""):
    RESULTS.append((name, bool(condition), detail))
    mark = "✅" if condition else "❌"
    print(f"  {mark} {name}" + (f"  — {detail}" if detail and not condition else ""))


def make_pdf(path: Path, pages=5, text="Hello PDFeverything"):
    doc = fitz.open()
    for i in range(pages):
        page = doc.new_page()
        page.insert_text((72, 72), f"{text} — page {i + 1}", fontsize=14)
        if i == 0:
            page.insert_text((72, 120), "SEARCHABLE NEEDLE", fontsize=12)
    doc.save(path)
    doc.close()
    return path


TMP = Path(tempfile.mkdtemp(prefix="pdfeverything_tests_"))
SRC = make_pdf(TMP / "src.pdf", 5)

# ═══════════════════════════════════════════════════════════
print("\n═══ 1. Page-range parser ═══")
check("simple list", parse_page_ranges("1,3,5", one_based=True) == [0, 2, 4])
check("ascending range", parse_page_ranges("2-4", one_based=True) == [1, 2, 3])
check("reversed range normalised", parse_page_ranges("4-2", one_based=True) == [1, 2, 3])
check("full-width comma", parse_page_ranges("1，3", one_based=True) == [0, 2])
check("en dash with spaces", parse_page_ranges("1 – 3", one_based=True) == [0, 1, 2])
check("ellipsis range", parse_page_ranges("1..3", one_based=True) == [0, 1, 2])
check("'all' expands", parse_page_ranges("all", total=4, one_based=True) == [0, 1, 2, 3])
check("empty string -> []", parse_page_ranges("   ", one_based=True) == [])
check("out-of-range dropped", parse_page_ranges("1,99", total=5, one_based=True) == [0])
check("zero dropped", parse_page_ranges("0", total=5, one_based=True) == [])
for bad in ("abc", "1-2-3", "x-y"):
    try:
        parse_page_ranges(bad, one_based=True)
        check(f"reject {bad!r}", False, "no ValueError raised")
    except ValueError:
        check(f"reject {bad!r}", True)
check("format round-trip", format_page_ranges([0, 1, 2, 4, 5]) == "1-3, 5-6")

# ═══════════════════════════════════════════════════════════
print("\n═══ 2. PdfOperator ═══")
info = PdfOperator.get_info(SRC)
check("get_info pages", info["pages"] == 5, str(info.get("pages")))
check("get_info size", info["size_bytes"] > 0)

merged = TMP / "merged.pdf"
PdfOperator.merge([SRC, SRC], merged)
check("merge -> 10 pages", len(fitz.open(merged)) == 10)

out_dir = TMP / "split"
parts = PdfOperator.split(SRC, out_dir)
check("split -> 5 files", len(parts) == 5 and all(p.exists() for p in parts))

ranged_dir = TMP / "split_ranges"
parts = PdfOperator.split(SRC, ranged_dir, [(1, 2), (4, 5)])
check("split by ranges", [len(fitz.open(p)) for p in parts] == [2, 2])

txt = TMP / "out.txt"
content = PdfOperator.extract_text(SRC, txt)
check("extract_text writes file", txt.exists() and len(content) > 0)
check("extract_text keeps text", "Hello PDFeverything" in content)

pwd_in = TMP / "enc.pdf"
PdfOperator.encrypt(SRC, pwd_in, "s3cret")
locked = fitz.open(pwd_in)
check("encrypt locks document", locked.needs_pass)
locked.close()

pwd_out = TMP / "dec.pdf"
PdfOperator.decrypt(pwd_in, pwd_out, "s3cret")
check("decrypt restores readable pdf", not fitz.open(pwd_out).needs_pass)

try:
    PdfOperator.decrypt(pwd_in, TMP / "nope.pdf", "wrong")
    check("decrypt rejects wrong password", False, "no exception")
except ValueError:
    check("decrypt rejects wrong password", True)

rot = TMP / "rot.pdf"
PdfOperator.rotate(SRC, rot, 90, [1, 2])
rotations = [p.rotation for p in fitz.open(rot)]
check("rotate only listed pages", rotations == [90, 90, 0, 0, 0], str(rotations))

rot_all = TMP / "rot_all.pdf"
PdfOperator.rotate(SRC, rot_all, 180, None)
check("rotate None = all pages",
      [p.rotation for p in fitz.open(rot_all)] == [180] * 5)

empty_rot = TMP / "rot_empty.pdf"
PdfOperator.rotate(SRC, empty_rot, 90, [])
check("rotate [] is a no-op (UI must guard this)",
      [p.rotation for p in fitz.open(empty_rot)] == [0] * 5)

img_dir = TMP / "imgs"
page = fitz.open()
p = page.new_page()
p.insert_image(fitz.Rect(50, 50, 200, 200), pixmap=fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 40, 40), 0))
page.save(TMP / "withimg.pdf")
page.close()
count = PdfOperator.extract_images(TMP / "withimg.pdf", img_dir)
check("extract_images finds embedded image", count >= 1, f"count={count}")

pngs = TMP / "pngs"
n = PdfOperator.to_images(SRC, pngs, dpi=72)
check("to_images renders every page", n == 5 and len(list(pngs.glob("*.png"))) == 5)

img_pdf = TMP / "from_img.pdf"
PdfOperator.from_images(sorted(pngs.glob("*.png"))[:3], img_pdf)
check("from_images builds 3-page pdf", len(fitz.open(img_pdf)) == 3)

small = TMP / "small.pdf"
res = PdfOperator.compress(SRC, small)
check("compress returns metrics", {"before_bytes", "after_bytes", "ratio"} <= set(res))
check("compress output readable", len(fitz.open(small)) == 5)

docx = TMP / "out.docx"
pages = PdfOperator.to_word(SRC, docx)
check("to_word produces docx", docx.exists() and pages == 5)

pptx = TMP / "out.pptx"
pages = PdfOperator.to_ppt(SRC, pptx, dpi=72)
check("to_ppt produces pptx", pptx.exists() and pages == 5)

xlsx = TMP / "out.xlsx"
sheets = PdfOperator.to_excel(SRC, xlsx)
check("to_excel produces xlsx", xlsx.exists() and sheets >= 1)

check("format_bytes", format_bytes(1536) == "1.5 KB", format_bytes(1536))
check("category pdf", get_file_category(Path("a.PDF")) == "pdf")

# ═══════════════════════════════════════════════════════════
print("\n═══ 3. i18n invariants ═══")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from gui.i18n import T, tr  # noqa: E402

check("every key has zh+en", all({"zh", "en"} == set(v) for v in T.values()))
missing = [k for k in T if not tr(k, lang="en") or not tr(k, lang="zh")]
check("no empty translations", not missing, str(missing[:5]))
# A positional placeholder reached with kwargs used to raise IndexError inside a
# Qt slot, which PyQt6 turns into a process abort. tr() must never raise.
raised = []
for key in T:
    for kwargs in ({}, {"e": "x"}, {"count": 1}, {"bogus": 1}):
        try:
            tr(key, **kwargs)
        except Exception as exc:  # noqa: BLE001
            raised.append((key, kwargs, type(exc).__name__))
check("tr() never raises", not raised, str(raised[:5]))
pos_ph = [k for k, v in T.items() if "{}" in v.get("en", "")]
check("no positional placeholders left", not pos_ph, str(pos_ph))
check("menu_merge translated", tr("menu_merge", lang="en") != "menu_merge")

# ═══════════════════════════════════════════════════════════
print("\n═══ 4. CLI wiring ═══")
import main as entry  # noqa: E402
import pdf_tool  # noqa: E402

parser_cmds = set()
for line in (ROOT / "pdf_tool.py").read_text().splitlines():
    line = line.strip()
    if line.startswith('sub.add_parser("'):
        parser_cmds.add(line.split('"')[1])
check("CLI_COMMANDS covers pdf_tool commands",
      parser_cmds <= entry.CLI_COMMANDS,
      f"missing: {sorted(parser_cmds - entry.CLI_COMMANDS)}")
helped = {c for c in entry.CLI_COMMANDS if f"    {c} " in entry.HELP_TEXT}
check("HELP_TEXT documents most commands",
      len(helped) >= len(entry.CLI_COMMANDS) - 12,
      f"undocumented: {sorted(entry.CLI_COMMANDS - helped)}")

run = subprocess.run([sys.executable, str(ROOT / "main.py"), "--version"],
                     capture_output=True, text=True, timeout=60)
check("--version works", run.returncode == 0 and "v" in run.stdout, run.stdout.strip())

run = subprocess.run([sys.executable, str(ROOT / "main.py"), "info", "-i", str(SRC)],
                     capture_output=True, text=True, timeout=120)
check("CLI info end-to-end", run.returncode == 0 and "页数" in run.stdout,
      run.stdout[:200] + run.stderr[:200])

# ═══════════════════════════════════════════════════════════
print("\n═══ 5. MCP tool registry ═══")
sys.path.insert(0, str(ROOT / "mcp"))
from server import TOOLS, _run_tool  # noqa: E402

names = [t["name"] for t in TOOLS]
check("tool names unique", len(names) == len(set(names)))
check("every tool has an inputSchema", all("inputSchema" in t for t in TOOLS))
check("every tool has a description", all(t.get("description") for t in TOOLS))

mcp_out = TMP / "mcp_info.json"
out = _run_tool("pdf_info", {"input": str(SRC)})
check("pdf_info callable via MCP", "5" in str(out), str(out)[:200])

mcp_pages = TMP / "mcp_pages"
out = _run_tool("pdf_extract_text", {"input": str(SRC), "output": str(TMP / "mcp.txt")})
check("pdf_extract_text callable via MCP", (TMP / "mcp.txt").exists(), str(out)[:200])

# ═══════════════════════════════════════════════════════════
passed = sum(1 for _, ok, _ in RESULTS if ok)
total = len(RESULTS)
print("\n" + "=" * 56)
print(f"  {passed}/{total} passed" + (" ✅" if passed == total else " ❌"))
print("=" * 56)
for name, ok, detail in RESULTS:
    if not ok:
        print(f"  FAILED: {name} — {detail}")
sys.exit(0 if passed == total else 1)
