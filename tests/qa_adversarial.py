#!/usr/bin/env python3
"""Adversarial QA harness — robustness / accuracy / consistency probes.

Unlike the regression suites (which check that known behaviour keeps working),
this harness attacks the software: malformed input, boundary values, hostile
page ranges, cross-channel consistency, pixel-level accuracy oracles and
resource accounting.

Run:  .venv/bin/python tests/qa_adversarial.py
Exit: 0 when every probe passes, 1 when any probe fails.

Each probe prints one line. A probe that fails prints the concrete evidence,
so a failure here is directly actionable.
"""
import io
import json
import os
import resource
import shutil
import subprocess
import sys
import tempfile
import time
import traceback
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

import fitz  # noqa: E402
from PIL import Image  # noqa: E402

PASS, FAIL = 0, 0
FAILURES: list = []
WORK = Path(tempfile.mkdtemp(prefix="pdfe_qa_"))


def check(ok, name, detail=""):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f"  \u2705 {name}")
    else:
        FAIL += 1
        FAILURES.append((name, detail))
        print(f"  \u274c {name}" + (f"\n        → {detail}" if detail else ""))


def section(title):
    print(f"\n\u2550\u2550\u2550 {title} \u2550\u2550\u2550")


def make_pdf(path: Path, pages: int = 3, text: str = "hello world",
             with_toc: bool = False, encrypt: str = None,
             image: bool = False, table: bool = False, cjk: bool = False):
    doc = fitz.open()
    for i in range(pages):
        page = doc.new_page(width=595, height=842)
        if cjk:
            page.insert_text((72, 100 + i * 20), f"\u7b2c{i + 1}\u9875 \u4e2d\u6587\u6d4b\u8bd5",
                             fontname="china-s", fontsize=14)
        else:
            page.insert_text((72, 100), f"Page {i + 1} {text}", fontsize=14)
            page.insert_text((72, 140), f"alpha beta gamma {i + 1}", fontsize=12)
        if image and i == 0:
            pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 120, 90))
            pix.set_rect(pix.irect, (255, 0, 0))
            page.insert_image(fitz.Rect(72, 200, 272, 350), pixmap=pix)
        if table and i == 0:
            for r in range(4):
                y = 400 + r * 24
                page.draw_line(fitz.Point(72, y), fitz.Point(400, y))
            for c in range(3):
                x = 72 + c * 110
                page.draw_line(fitz.Point(x, 400), fitz.Point(x, 472))
            for r in range(3):
                for c in range(3):
                    page.insert_text((80 + c * 110, 418 + r * 24), f"r{r}c{c}", fontsize=10)
    if with_toc:
        doc.set_toc([[1, "Chapter 1", 1], [2, "Section 1.1", 2],
                     [1, "Chapter 2", min(3, pages)]])
    if encrypt:
        doc.save(str(path), encryption=fitz.PDF_ENCRYPT_AES_256,
                 user_pw=encrypt, owner_pw=encrypt + "_o")
    else:
        doc.save(str(path))
    doc.close()
    return path


# ══════════════════════════════════════════════════════════════════
section("QA1: page-range parser — hostile and boundary input")
# ══════════════════════════════════════════════════════════════════
from core.utils import parse_page_ranges, format_page_ranges, format_bytes  # noqa: E402

# Equivalences that must hold for the documented grammar
equiv = [
    ("1-3", [0, 1, 2]),
    (" 1 - 3 ", [0, 1, 2]),
    ("1\u20133", [0, 1, 2]),        # en dash
    ("1\u20143", [0, 1, 2]),        # em dash
    ("1~3", [0, 1, 2]),
    ("1..3", [0, 1, 2]),
    ("1,1,1", [0]),
    ("3,1,2", [0, 1, 2]),           # sorted + deduped
    ("1\uff0c3", [0, 2]),           # full-width comma
    ("1\u30013", [0, 2]),           # ideographic comma
    ("all", [0, 1, 2]),
    ("*", [0, 1, 2]),
    ("3-1", [0, 1, 2]),             # reversed range still means 1..3
]
for spec, want in equiv:
    try:
        got = parse_page_ranges(spec, total=3, one_based=True)
        check(got == want, f"parse {spec!r} → {want}", f"got {got}")
    except Exception as e:
        check(False, f"parse {spec!r} → {want}", f"raised {type(e).__name__}: {e}")

# Out-of-range must be dropped, never crash. Negative specs are not out-of-range
# pages but malformed input, so they are refused with a clear message instead.
for spec in ["99", "0", "1-999", "999-1000"]:
    try:
        got = parse_page_ranges(spec, total=3, one_based=True)
        check(all(0 <= p < 3 for p in got), f"clamp {spec!r} into range", f"got {got}")
    except Exception as e:
        check(False, f"clamp {spec!r} into range", f"raised {type(e).__name__}: {e}")

# Garbage must raise ValueError (a message the UI can show), not crash silently.
# "1-" belongs here: reading it as "1" acted on a different set of pages than
# the user typed.
for spec in ["abc", "1-2-3", "1,,x", "1-", "-5", "-1", "p", "\u4e00-\u4e8c"]:
    try:
        got = parse_page_ranges(spec, total=3, one_based=True)
        # returning empty is acceptable only if it is genuinely a no-match
        check(got == [], f"garbage {spec!r} → clean empty/error", f"got {got}")
    except ValueError:
        check(True, f"garbage {spec!r} → clean empty/error")
    except Exception as e:
        check(False, f"garbage {spec!r} → clean empty/error",
              f"raised {type(e).__name__}: {e}")

check(parse_page_ranges(None) == [], "None spec → empty list")
check(parse_page_ranges("") == [] and parse_page_ranges("   ") == [],
      "blank spec → empty list")
check(parse_page_ranges([3, 1, 2], one_based=True) == [0, 1, 2], "list spec sorted")
try:
    big = parse_page_ranges("1-200001", one_based=True)
    check(False, "absurd range refused", f"accepted {len(big)} pages")
except ValueError:
    check(True, "absurd range refused")

# format_page_ranges round-trip
for ordinals in ([0, 1, 2, 4], [], [5], [0, 2, 4, 6]):
    txt = format_page_ranges(ordinals)
    if txt:
        back = parse_page_ranges(txt, one_based=True)
        check(back == sorted(set(ordinals)), f"round-trip {ordinals} → {txt!r}", f"got {back}")
    else:
        check(ordinals == [], "empty ordinals → empty string")

check(format_bytes(0) == "0.0 B", "format_bytes(0)")
check(format_bytes(1536).startswith("1.5"), "format_bytes(1536)")


# ══════════════════════════════════════════════════════════════════
section("QA2: PdfOperator — malformed and hostile input")
# ══════════════════════════════════════════════════════════════════
from core.pdf_ops import PdfOperator  # noqa: E402

good = make_pdf(WORK / "good3.pdf", pages=3)
big = make_pdf(WORK / "big30.pdf", pages=30, with_toc=True)

# 0-byte / truncated / non-PDF files must be reported, not half-processed
empty = WORK / "empty.pdf"
empty.write_bytes(b"")
trunc = WORK / "trunc.pdf"
trunc.write_bytes(good.read_bytes()[:400])
notpdf = WORK / "fake.pdf"
notpdf.write_bytes(b"%PDF-1.4\nthis is not really a pdf at all\n" * 3)

for bad, label in ((empty, "0-byte"), (trunc, "truncated"), (notpdf, "fake header")):
    try:
        PdfOperator.extract_text(bad, WORK / "x.txt")
        check(False, f"extract_text rejects {label} PDF")
    except Exception as e:
        check(not isinstance(e, (SystemError, MemoryError)),
              f"extract_text rejects {label} PDF",
              f"{type(e).__name__}: {e}")

# get_info must always answer, even for a corrupt file
for bad, label in ((empty, "0-byte"), (trunc, "truncated"), (notpdf, "fake")):
    try:
        info = PdfOperator.get_info(bad)
        check(isinstance(info, dict) and "pages" in info, f"get_info survives {label} PDF")
    except Exception as e:
        check(False, f"get_info survives {label} PDF", f"{type(e).__name__}: {e}")

# Output into a non-existent nested directory must be created, not crash
nested = WORK / "a" / "b" / "c" / "out.txt"
try:
    PdfOperator.extract_text(good, nested)
    check(nested.exists(), "nested output directory auto-created")
except Exception as e:
    check(False, "nested output directory auto-created", f"{type(e).__name__}: {e}")

# ── merge ──
try:
    PdfOperator.merge([good, good], WORK / "merged.pdf")
    check(len(fitz.open(WORK / "merged.pdf")) == 6, "merge 3+3 pages = 6")
except Exception as e:
    check(False, "merge 3+3 pages = 6", f"{type(e).__name__}: {e}")

try:
    PdfOperator.merge([], WORK / "none.pdf")
    check(False, "merge with empty input list is refused")
except (ValueError, IndexError) as e:
    check(True, "merge with empty input list is refused")
except Exception as e:
    check(False, "merge with empty input list is refused", f"{type(e).__name__}: {e}")

try:
    PdfOperator.merge([good, WORK / "missing.pdf"], WORK / "partial.pdf")
    check(False, "merge missing file does not leave a partial output")
except Exception as e:
    check(not (WORK / "partial.pdf").exists(),
          "merge missing file does not leave a partial output",
          f"partial output exists (raised {type(e).__name__})")

# ── split ──
outdir = WORK / "split"
outs = PdfOperator.split(big, outdir, [(1, 10), (11, 20), (21, 30)])
check(len(outs) == 3, "split 3 ranges → 3 files", f"got {len(outs)}")
check(all(len(fitz.open(o)) == 10 for o in outs), "each split file has 10 pages")
outs2 = PdfOperator.split(big, WORK / "split2", [(1, 5), (999, 1000)])
check(len(outs2) == 1, "split out-of-range range is skipped, not emitted empty",
      f"got {len(outs2)} files")
outs3 = PdfOperator.split(good, WORK / "split3")
check(len(outs3) == 3, "split default = one file per page")

# ── rotate ──
for angle in (90, 180, 270):
    o = WORK / f"rot{angle}.pdf"
    PdfOperator.rotate(good, o, angle)
    rots = {fitz.open(o)[i].rotation for i in range(3)}
    check(rots == {angle}, f"rotate {angle} applied to every page", f"got {rots}")

for bad_angle in (0, 45, -90, 360):
    try:
        PdfOperator.rotate(good, WORK / "rotbad.pdf", bad_angle)
        check(False, f"rotate {bad_angle} refused")
    except ValueError:
        check(True, f"rotate {bad_angle} refused")
    except Exception as e:
        check(False, f"rotate {bad_angle} refused", f"{type(e).__name__}: {e}")

# rotate with an explicit page list is 1-based in the public API contract
o = WORK / "rot1.pdf"
PdfOperator.rotate(good, o, 90, pages=[2])
d = fitz.open(o)
check([d[i].rotation for i in range(3)] == [0, 90, 0],
      "rotate pages=[2] rotates only page 2", f"got {[d[i].rotation for i in range(3)]}")
d.close()

# ── encrypt / decrypt round trip ──
enc = WORK / "enc.pdf"
PdfOperator.encrypt(good, enc, "s3cret")
d = fitz.open(enc)
check(d.needs_pass and d.authenticate("s3cret"), "encrypted output opens with its password")
d.close()
try:
    PdfOperator.encrypt(good, WORK / "enc0.pdf", "")
    check(False, "empty password refused")
except ValueError:
    check(True, "empty password refused")

try:
    PdfOperator.encrypt(good, WORK / "encsp.pdf", "   ")
    check(False, "whitespace-only password refused")
except ValueError:
    check(True, "whitespace-only password refused")

dec = WORK / "dec.pdf"
PdfOperator.decrypt(enc, dec, "s3cret")
d = fitz.open(dec)
check(not d.needs_pass, "decrypted output needs no password")
check(len(d) == 3, "decrypted output keeps 3 pages")
d.close()
try:
    PdfOperator.decrypt(enc, WORK / "decbad.pdf", "wrong")
    check(False, "wrong password refused")
except ValueError:
    check(True, "wrong password refused")
check(not (WORK / "decbad.pdf").exists(),
      "wrong password leaves no output file")

# get_info on an encrypted file reports encryption + page count
info = PdfOperator.get_info(enc)
check(info["encrypted"] is True, "get_info flags encrypted file")
check(info["pages"] == 3, "get_info reports page count of encrypted file",
      f"got {info['pages']}")

# ── text extraction accuracy ──
cjk_pdf = make_pdf(WORK / "cjk.pdf", pages=2, cjk=True)
cjk_txt = PdfOperator.extract_text(cjk_pdf, WORK / "cjk.txt")
check("中文测试" in cjk_txt, "CJK text extracted intact (no tofu/dots)",
      f"got {cjk_txt[:80]!r}")

# ── watermarks ──
try:
    PdfOperator.text_watermark(good, WORK / "wm.pdf", "CONFIDENTIAL")
    check(len(fitz.open(WORK / "wm.pdf")) == 3, "text watermark keeps page count")
except Exception as e:
    check(False, "text watermark keeps page count", f"{type(e).__name__}: {e}")

try:
    PdfOperator.text_watermark(good, WORK / "wm_cjk.pdf", "机密文件")
    txt = fitz.open(WORK / "wm_cjk.pdf")[0].get_text()
    check("机密文件" in txt, "CJK watermark renders as real glyphs", f"page text={txt[:60]!r}")
except Exception as e:
    check(False, "CJK watermark renders as real glyphs", f"{type(e).__name__}: {e}")

for bad_op in (-0.5, 1.5):
    try:
        PdfOperator.text_watermark(good, WORK / "wm_o.pdf", "X", opacity=bad_op)
        check(True, f"watermark opacity {bad_op} clamped")
    except Exception as e:
        check(False, f"watermark opacity {bad_op} clamped", f"{type(e).__name__}: {e}")

# ── page numbers ──
try:
    n = PdfOperator.add_page_numbers(big, WORK / "pn.pdf", template="第 {n} / {total} 页")
    txt = fitz.open(WORK / "pn.pdf")[0].get_text()
    check("第" in txt and "30" in txt, "CJK page-number template renders", f"got {txt[:60]!r}")
    check(n == 30, "page numbers stamped on all pages", f"got {n}")
except Exception as e:
    check(False, "CJK page-number template renders", f"{type(e).__name__}: {e}")

try:
    n = PdfOperator.add_page_numbers(big, WORK / "pn2.pdf", pages=[0, 2], start_number=5)
    check(n == 2, "page numbers honour the page subset", f"got {n}")
except Exception as e:
    check(False, "page numbers honour the page subset", f"{type(e).__name__}: {e}")

# ── nup ──
for per in (2, 4, 6, 8, 9, 16):
    try:
        sheets = PdfOperator.nup(big, WORK / f"nup{per}.pdf", per_sheet=per)
        want = (30 + per - 1) // per
        check(sheets == want, f"nup {per}-up → {want} sheets", f"got {sheets}")
    except Exception as e:
        check(False, f"nup {per}-up → {(30 + per - 1) // per} sheets",
              f"{type(e).__name__}: {e}")

# ── insert / extract / delete ──
o = WORK / "ins.pdf"
PdfOperator.insert_pages(good, make_pdf(WORK / "src2.pdf", pages=2), o, at=1)
check(len(fitz.open(o)) == 5, "insert 2 pages at index 1 → 5 pages")
o = WORK / "ins_append.pdf"
PdfOperator.insert_pages(good, WORK / "src2.pdf", o, at=-1)
check(len(fitz.open(o)) == 5, "insert at -1 appends")

o = WORK / "ext.pdf"
PdfOperator.extract_pages(big, o, [0, 5, 29])
check(len(fitz.open(o)) == 3, "extract 3 non-contiguous pages")
try:
    PdfOperator.extract_pages(big, WORK / "ext0.pdf", [])
    check(False, "extract with empty page list refused")
except ValueError:
    check(True, "extract with empty page list refused")

try:
    PdfOperator.extract_pages(big, WORK / "extoob.pdf", [500])
    check(False, "extract all-out-of-range refused")
except ValueError:
    check(True, "extract all-out-of-range refused")

o = WORK / "del.pdf"
left = PdfOperator.delete_pages(big, o, [0, 1])
check(left == 28, "delete 2 of 30 → 28 left", f"got {left}")
try:
    PdfOperator.delete_pages(big, WORK / "delall.pdf", list(range(30)))
    check(False, "deleting every page refused")
except ValueError:
    check(True, "deleting every page refused")

# ── metadata round trip ──
o = WORK / "meta.pdf"
res = PdfOperator.set_metadata(good, o, {"title": "T", "author": "A", "keywords": "k1,k2"})
d = fitz.open(o)
check(d.metadata.get("title") == "T" and d.metadata.get("author") == "A",
      "metadata round trip", f"got {d.metadata}")
d.close()
try:
    PdfOperator.set_metadata(good, WORK / "meta_bad.pdf", {"bogus": "x"})
    check(False, "unknown metadata key refused")
except ValueError:
    check(True, "unknown metadata key refused")
try:
    PdfOperator.set_metadata(good, WORK / "meta_none.pdf", {})
    check(False, "empty metadata dict refused")
except ValueError:
    check(True, "empty metadata dict refused")

# ── compress: lossless must not change visible content ──
img_pdf = make_pdf(WORK / "img.pdf", pages=1, image=True)
res_ll = PdfOperator.compress(img_pdf, WORK / "ll.pdf", mode="lossless")
t_before = fitz.open(img_pdf)[0].get_text()
t_after = fitz.open(WORK / "ll.pdf")[0].get_text()
check(t_before == t_after, "lossless compress preserves text exactly")
try:
    PdfOperator.compress(img_pdf, WORK / "bad.pdf", mode="nonsense")
    check(False, "unknown compress mode refused")
except ValueError:
    check(True, "unknown compress mode refused")

# ── to_excel / to_word on a table PDF ──
tbl = make_pdf(WORK / "tbl.pdf", pages=1, table=True)
try:
    sheets = PdfOperator.to_excel(tbl, WORK / "t.xlsx")
    check(sheets >= 1, "to_excel finds at least one sheet", f"got {sheets}")
except Exception as e:
    check(False, "to_excel finds at least one sheet", f"{type(e).__name__}: {e}")

try:
    PdfOperator.to_word(tbl, WORK / "t.docx")
    check((WORK / "t.docx").stat().st_size > 1000, "to_word produces a real docx")
except Exception as e:
    check(False, "to_word produces a real docx", f"{type(e).__name__}: {e}")

try:
    PdfOperator.to_ppt(tbl, WORK / "t.pptx", dpi=72)
    check((WORK / "t.pptx").stat().st_size > 1000, "to_ppt produces a real pptx")
except Exception as e:
    check(False, "to_ppt produces a real pptx", f"{type(e).__name__}: {e}")

# ── images round trip ──
try:
    n = PdfOperator.extract_images(img_pdf, WORK / "imgs")
    check(n == 1, "extract_images finds the embedded image", f"got {n}")
except Exception as e:
    check(False, "extract_images finds the embedded image", f"{type(e).__name__}: {e}")

try:
    n = PdfOperator.to_images(good, WORK / "pages", dpi=150)
    check(n == 3, "to_images renders every page", f"got {n}")
    check(len(list((WORK / "pages").glob("*.png"))) == 3, "to_images wrote 3 PNGs")
except Exception as e:
    check(False, "to_images renders every page", f"{type(e).__name__}: {e}")

# PNG with alpha, and a 1x1 image
Image.new("RGBA", (40, 40), (255, 0, 0, 128)).save(WORK / "alpha.png")
Image.new("P", (20, 20)).save(WORK / "pal.png")
Image.new("RGB", (1, 1), (0, 0, 255)).save(WORK / "tiny.jpg")
for name in ("alpha.png", "pal.png", "tiny.jpg"):
    try:
        PdfOperator.from_images([WORK / name], WORK / f"from_{name}.pdf")
        check(len(fitz.open(WORK / f"from_{name}.pdf")) == 1, f"from_images handles {name}")
    except Exception as e:
        check(False, f"from_images handles {name}", f"{type(e).__name__}: {e}")


# ══════════════════════════════════════════════════════════════════
section("QA3: search accuracy")
# ══════════════════════════════════════════════════════════════════
from core.search import search_pdf, get_outline  # noqa: E402

s = search_pdf(good, "alpha")
check(s.count == 3, "finds one hit per page", f"got {s.count}")
check(s.pages_with_hits() == [0, 1, 2], "reports the right pages",
      f"got {s.pages_with_hits()}")
check(all(h.context for h in s.hits), "every hit carries context")
check(all(len(h.rect) == 4 and h.rect[2] > h.rect[0] for h in s.hits),
      "every hit carries a non-empty rect")

s_ci = search_pdf(good, "ALPHA")
check(s_ci.count == 3, "case-insensitive by default", f"got {s_ci.count}")
s_cs = search_pdf(good, "ALPHA", case_sensitive=True)
check(s_cs.count == 0, "case-sensitive finds nothing for wrong case", f"got {s_cs.count}")
s_cs2 = search_pdf(good, "alpha", case_sensitive=True)
check(s_cs2.count == 3, "case-sensitive matches exact case", f"got {s_cs2.count}")

s_ww = search_pdf(good, "alph", whole_word=True)
check(s_ww.count == 0, "whole-word rejects a prefix", f"got {s_ww.count}")
s_ww2 = search_pdf(good, "alpha", whole_word=True)
check(s_ww2.count == 3, "whole-word accepts the whole word", f"got {s_ww2.count}")

s_lim = search_pdf(good, "alpha", pages=[1])
check(s_lim.count == 1 and s_lim.hits[0].page == 1, "page-limited search",
      f"got {s_lim.count} hits on {[h.page for h in s_lim.hits]}")

s_tr = search_pdf(big, "alpha", max_hits=2)
check(s_tr.count == 2 and s_tr.truncated, "max_hits truncation flags truncated=True",
      f"count={s_tr.count} truncated={s_tr.truncated}")

s_empty = search_pdf(good, "   ")
check(s_empty.count == 0, "blank query → no hits")
s_miss = search_pdf(good, "zzzznotpresent")
check(s_miss.count == 0, "absent query → no hits")

# regex metacharacters must be treated literally, never raise
for q in [".*", "(", "[a-z]", "a|b", "\\", "$^"]:
    try:
        search_pdf(good, q)
        check(True, f"regex metachar query {q!r} handled")
    except Exception as e:
        check(False, f"regex metachar query {q!r} handled", f"{type(e).__name__}: {e}")

# encrypted PDF must give a clear error, not a crash
try:
    search_pdf(enc, "alpha")
    check(False, "searching an encrypted PDF is refused cleanly")
except ValueError as e:
    check("密码" in str(e) or "password" in str(e).lower(),
          "searching an encrypted PDF is refused cleanly", f"msg={e}")
except Exception as e:
    check(False, "searching an encrypted PDF is refused cleanly", f"{type(e).__name__}: {e}")

# outline
entries = get_outline(big)
check(len(entries) == 2, "outline has 2 top-level entries", f"got {len(entries)}")
flat = [e for e in entries[0].flatten()]
check(len(flat) == 2 and flat[1].level == 1, "outline nesting preserved")
check(entries[0].page == 0, "outline target page is 0-based 0", f"got {entries[0].page}")
check(get_outline(good) == [], "PDF without bookmarks → empty outline")


# ══════════════════════════════════════════════════════════════════
section("QA4: page editor — undo/redo/journal integrity")
# ══════════════════════════════════════════════════════════════════
from core.page_editor import PdfPageEditor  # noqa: E402

src = make_pdf(WORK / "edit.pdf", pages=6)
ed = PdfPageEditor(src)
ed.delete_pages([0])
check(ed.page_count == 5, "editor delete_pages works", f"got {ed.page_count}")
desc = ed.undo()
check(desc and ed.page_count == 6, "editor undo restores the page count",
      f"desc={desc} pages={ed.page_count}")
desc = ed.redo()
check(ed.page_count == 5, "editor redo re-applies the delete", f"pages={ed.page_count}")
ed.close()

# Journal persistence across "processes" (fresh editor instances). An in-place
# edit is the supported flow: PDFs carry no lineage, so an edit written to a
# *different* file legitimately starts a fresh document with no history.
PdfPageEditor.sweep_stale_journals(0)
j1 = make_pdf(WORK / "journal.pdf", pages=5)
e1 = PdfPageEditor(j1)
e1.load_journal()
e1.delete_pages([0])
e1.save_journal()
e1.save(j1)                       # in place: same document, same journal
e1.close()
check(len(fitz.open(j1)) == 4, "in-place delete applied",
      f"got {len(fitz.open(j1))}")

e2 = PdfPageEditor(j1)
e2.load_journal()
check(len(e2.history) >= 2, "journal survives across editor instances",
      f"history={e2.history}")
back = e2.undo()
check(back is not None, "undo is available in the next session", f"desc={back}")
e2.save(j1)
e2.save_journal()
e2.close()
check(len(fitz.open(j1)) == 5,
      "cross-session undo restored the original page count",
      f"got {len(fitz.open(j1))}")

e3 = PdfPageEditor(j1)
e3.load_journal()
fwd = e3.redo()
e3.save(j1)
e3.close()
check(fwd is not None and len(fitz.open(j1)) == 4,
      "cross-session redo re-applies the delete",
      f"desc={fwd} pages={len(fitz.open(j1))}")

# rotate_pages must reject an unsupported angle instead of silently doing nothing
e3 = PdfPageEditor(make_pdf(WORK / "rot_ed.pdf", pages=3))
e3.rotate_pages([0], 45)
check(e3.page_rotation(0) == 0, "editor refuses a 45° rotation")
e3.rotate_pages([0], 90)
check(e3.page_rotation(0) == 90, "editor applies a 90° rotation",
      f"got {e3.page_rotation(0)}")
e3.close()

# move_pages integrity: the multiset of page contents must be preserved
mv_src = fitz.open()
for i in range(5):
    p = mv_src.new_page()
    p.insert_text((72, 100), f"UNIQ{i}", fontsize=20)
mv_path = WORK / "move.pdf"
mv_src.save(mv_path)
mv_src.close()
e4 = PdfPageEditor(mv_path)
e4.move_pages([0], 2)
e4.save(WORK / "moved.pdf")
e4.close()
d = fitz.open(WORK / "moved.pdf")
moved_text = [d[i].get_text().strip() for i in range(len(d))]
d.close()
check(len(moved_text) == 5 and sorted(moved_text) == [f"UNIQ{i}" for i in range(5)],
      "move_pages preserves every page exactly once", f"got {moved_text}")

# journal must not grow without bound in memory
e5 = PdfPageEditor(make_pdf(WORK / "deep.pdf", pages=4))
for i in range(80):
    e5.rotate_pages([0], 90)
check(len(e5._journal_states) <= 50,
      "journal state list is capped (memory bound)", f"got {len(e5._journal_states)}")
e5.close()


# ══════════════════════════════════════════════════════════════════
section("QA5: CLI — exit codes, malformed args, output correctness")
# ══════════════════════════════════════════════════════════════════
PY = str(ROOT / ".venv" / "bin" / "python")
MAIN = str(ROOT / "main.py")
ENV = dict(os.environ, PYTHONPATH=str(ROOT))


def run_cli(args, timeout=180):
    return subprocess.run([PY, MAIN] + args, capture_output=True, text=True,
                          cwd=str(ROOT), timeout=timeout, env=ENV)


r = run_cli(["--version"])
check(r.returncode == 0 and "v" in r.stdout, "--version works", r.stdout.strip())

r = run_cli(["-h"])
check(r.returncode == 0 and "merge" in r.stdout, "-h prints help")

r = run_cli(["info", "-i", str(good)])
check(r.returncode == 0 and "页数: 3" in r.stdout, "info CLI reports 3 pages",
      r.stdout.strip()[:120])

r = run_cli(["info", "-i", str(WORK / "nope.pdf")])
check(r.returncode != 0 and "❌" in (r.stdout + r.stderr),
      "info on a missing file exits non-zero with a message",
      f"rc={r.returncode} out={r.stdout!r} err={r.stderr!r}")

r = run_cli(["not-a-command"])
check(r.returncode != 0, "unknown command exits non-zero",
      f"rc={r.returncode} out={r.stdout!r}")
check("Unknown command" in (r.stdout + r.stderr),
      "unknown command explains itself instead of opening the GUI",
      f"out={r.stdout!r} err={r.stderr!r}")

# search --json output must be valid JSON on stdout
r = run_cli(["search", "-i", str(good), "-q", "alpha", "--json"])
try:
    payload = json.loads(r.stdout)
    check(payload.get("matches") == 3, "search --json is parseable and correct",
          f"got {payload}")
except Exception as e:
    check(False, "search --json is parseable and correct",
          f"{type(e).__name__}: stdout={r.stdout[:200]!r}")

# a bad page range must fail loudly, not produce a truncated file
r = run_cli(["delete-pages-fitz", "-i", str(good), "-o", str(WORK / "cli_del.pdf"),
             "--pages", "garbage"])
check(r.returncode != 0, "CLI rejects a garbage page range with non-zero exit",
      f"rc={r.returncode} out={r.stdout!r} err={r.stderr!r}")

r = run_cli(["extract-pages-fitz", "-i", str(good), "-o", str(WORK / "cli_ex.pdf"),
             "--pages", "1-2"])
check(r.returncode == 0 and len(fitz.open(WORK / "cli_ex.pdf")) == 2,
      "extract-pages-fitz emits a 2-page PDF")

# page-undo with no history must fail loudly
fresh = make_pdf(WORK / "fresh_nojournal.pdf", pages=3)
r = run_cli(["page-undo", "-i", str(fresh), "-o", str(WORK / "u.pdf")])
check(r.returncode != 0, "page-undo without history exits non-zero",
      f"rc={r.returncode} out={r.stdout!r}")

# CLI must not print anything that breaks a JSON consumer
r = run_cli(["outline", "-i", str(big), "--json"])
try:
    payload = json.loads(r.stdout)
    check(payload.get("count") == 2, "outline --json parseable", f"got {r.stdout[:120]!r}")
except Exception as e:
    check(False, "outline --json parseable", f"{type(e).__name__}: {r.stdout[:200]!r}")


# ══════════════════════════════════════════════════════════════════
section("QA6: MCP — protocol conformance and tool correctness")
# ══════════════════════════════════════════════════════════════════


def mcp_session(requests, timeout=180):
    """Send JSON-RPC lines, return the parsed responses."""
    proc = subprocess.run(
        [PY, str(ROOT / "mcp" / "server.py")],
        input="\n".join(json.dumps(r) for r in requests) + "\n",
        capture_output=True, text=True, cwd=str(ROOT), timeout=timeout, env=ENV)
    out = []
    for line in proc.stdout.splitlines():
        line = line.strip()
        if line:
            out.append(json.loads(line))
    return out, proc


resp, proc = mcp_session([
    {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
    {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
])
check(len(resp) == 2, "initialize + tools/list answered with exactly 2 frames",
      f"got {len(resp)}: {[list(r.keys()) for r in resp]}")
tools = resp[1]["result"]["tools"]
check(len(tools) == 29, "MCP exposes 29 tools", f"got {len(tools)}")
names = [t["name"] for t in tools]
check(len(names) == len(set(names)), "tool names unique")
check(all(t.get("inputSchema") for t in tools), "every tool declares an inputSchema")
check(all(t.get("description") for t in tools), "every tool has a description")

# notifications must never be answered
resp, proc = mcp_session([
    {"jsonrpc": "2.0", "method": "notifications/initialized"},
    {"jsonrpc": "2.0", "id": 9, "method": "ping"},
])
check(len(resp) == 1 and resp[0]["id"] == 9, "notification produced no response",
      f"got {len(resp)} frames")

# malformed line → -32700, and the server survives
resp, proc = mcp_session([
    {"jsonrpc": "2.0", "id": 1, "method": "initialize"},
    "NOT JSON AT ALL",
    {"jsonrpc": "2.0", "id": 3, "method": "ping"},
])
check(any(r.get("error", {}).get("code") == -32700 for r in resp),
      "malformed line → -32700", f"got {resp}")

# unknown method → -32601
resp, proc = mcp_session([
    {"jsonrpc": "2.0", "id": 1, "method": "no/such/method"},
])
check(resp and resp[0].get("error", {}).get("code") == -32601,
      "unknown method → -32601", f"got {resp}")

# a failing tool must return isError=true, not crash the server
resp, proc = mcp_session([
    {"jsonrpc": "2.0", "id": 1, "method": "initialize"},
    {"jsonrpc": "2.0", "id": 2, "method": "tools/call",
     "params": {"name": "pdf_info", "arguments": {"input": str(WORK / "gone.pdf")}}},
    {"jsonrpc": "2.0", "id": 3, "method": "ping"},
])
check(len(resp) == 3, "server survives a failing tool call", f"got {len(resp)} frames")
check(resp[1]["result"]["isError"] is True, "failing tool sets isError=true",
      f"got {resp[1]['result']}")

# real work through MCP
resp, proc = mcp_session([
    {"jsonrpc": "2.0", "id": 1, "method": "initialize"},
    {"jsonrpc": "2.0", "id": 2, "method": "tools/call",
     "params": {"name": "pdf_merge",
                "arguments": {"input_files": [str(good), str(good)],
                              "output": str(WORK / "mcp_merged.pdf")}}},
])
payload = json.loads(resp[1]["result"]["content"][0]["text"])
check(payload.get("success") and len(fitz.open(WORK / "mcp_merged.pdf")) == 6,
      "pdf_merge via MCP works", f"got {payload}")

# ── cross-channel page-range consistency (documented design rule) ──
spec = "1-2"
mcp_out = WORK / "mcp_ext.pdf"
resp, proc = mcp_session([
    {"jsonrpc": "2.0", "id": 1, "method": "initialize"},
    {"jsonrpc": "2.0", "id": 2, "method": "tools/call",
     "params": {"name": "pdf_extract_pages",
                "arguments": {"input": str(good), "output": str(mcp_out),
                              "pages": spec}}},
])
try:
    payload = json.loads(resp[1]["result"]["content"][0]["text"])
except Exception as e:
    payload = {"exception": f"{type(e).__name__}: {e}", "raw": resp[1]}
mcp_ok = bool(payload.get("success"))
mcp_pages = len(fitz.open(mcp_out)) if mcp_out.exists() else 0
check(mcp_ok and mcp_pages == 2,
      "MCP pdf_extract_pages accepts '1-2' (same grammar as CLI)",
      f"payload={payload}")

resp, proc = mcp_session([
    {"jsonrpc": "2.0", "id": 1, "method": "initialize"},
    {"jsonrpc": "2.0", "id": 2, "method": "tools/call",
     "params": {"name": "pdf_extract_pages",
                "arguments": {"input": str(good), "output": str(WORK / "mcp_ext2.pdf"),
                              "pages": "1, 2"}}},
])
try:
    payload = json.loads(resp[1]["result"]["content"][0]["text"])
except Exception as e:
    payload = {"exception": f"{type(e).__name__}: {e}"}
check(payload.get("success") is True,
      "MCP page ranges tolerate spaces (same grammar as CLI)", f"payload={payload}")


# ══════════════════════════════════════════════════════════════════
section("QA7: performance and resource ceilings")
# ══════════════════════════════════════════════════════════════════
def timed(fn, *a, **k):
    t0 = time.perf_counter()
    r = fn(*a, **k)
    return r, (time.perf_counter() - t0) * 1000


huge = make_pdf(WORK / "huge1000.pdf", pages=1000)
_, ms_info = timed(PdfOperator.get_info, huge)
check(ms_info < 400, f"get_info on a 1000-page PDF < 400ms (got {ms_info:.0f}ms)")

_, ms_outline = timed(get_outline, huge)
check(ms_outline < 400, f"get_outline on a 1000-page PDF < 400ms (got {ms_outline:.0f}ms)")

# get_info must not load every page object just to count pages
import tracemalloc  # noqa: E402
tracemalloc.start()
PdfOperator.get_info(huge)
_, peak = tracemalloc.get_traced_memory()
tracemalloc.stop()
check(peak < 20 * 1024 * 1024,
      f"get_info allocates <20MB on a 1000-page PDF (got {peak / 1e6:.1f}MB)")

# repeated operations must not leak file descriptors
def fd_count():
    return len(os.listdir(f"/dev/fd")) if os.path.isdir("/dev/fd") else 0

before_fd = fd_count()
for _ in range(30):
    PdfOperator.get_info(good)
    fitz.open(good).close()
after_fd = fd_count()
check(after_fd - before_fd < 5,
      f"no file-descriptor leak over 30 opens ({before_fd} → {after_fd})")

# search over a large document must stay reasonable
_, ms_search = timed(search_pdf, huge, "alpha")
check(ms_search < 4000, f"search over 1000 pages < 4s (got {ms_search:.0f}ms)")

# merge throughput
_, ms_merge = timed(PdfOperator.merge, [good] * 20, WORK / "perf_merge.pdf")
check(ms_merge < 5000, f"merge 20×3 pages < 5s (got {ms_merge:.0f}ms)")


# ══════════════════════════════════════════════════════════════════
section("QA8: lightweight-ness — no stray temp files or caches")
# ══════════════════════════════════════════════════════════════════
from core.utils import temp_dir as core_temp_dir, cleanup_temp_files  # noqa: E402

# a mixed merge must leave nothing behind in /tmp
mixed = make_pdf(WORK / "mixed_a.pdf", pages=2)
(WORK / "mixed_b.txt").write_text("plain text file\n" * 20, encoding="utf-8")
from core.merger import merge_mixed_files  # noqa: E402

tmp_before = set(p for p in Path(tempfile.gettempdir()).iterdir()
                 if p.name.startswith("pdf_merge_") or p.name.startswith("pdfeverything_"))
res = merge_mixed_files([mixed, WORK / "mixed_b.txt"], WORK / "mixed_out.pdf")
tmp_after = set(p for p in Path(tempfile.gettempdir()).iterdir()
                if p.name.startswith("pdf_merge_") or p.name.startswith("pdfeverything_"))
leaked = tmp_after - tmp_before
check(not leaked, "mixed merge leaves no temp files behind",
      f"leaked: {[p.name for p in leaked]}")
check(res["success"] and len(fitz.open(WORK / "mixed_out.pdf")) == 3,
      "mixed merge PDF+text = 3 pages", f"got {res}")

# a mixed merge where everything fails must not leave an output file
bad_txt = WORK / "bad.bin"
bad_txt.write_bytes(b"\x00\x01\x02")
try:
    merge_mixed_files([WORK / "bad.bin"], WORK / "never.pdf")
    check(False, "all-failed mixed merge raises and writes nothing")
except Exception:
    check(not (WORK / "never.pdf").exists(),
          "all-failed mixed merge raises and writes nothing")

cleanup_temp_files()


# ══════════════════════════════════════════════════════════════════
print("\n" + "=" * 60)
print(f"  {PASS}/{PASS + FAIL} adversarial probes passed"
      + ("" if not FAIL else f"  \u2014 {FAIL} FAILED"))
print("=" * 60)
if FAILURES:
    print("\nFailures (actionable):")
    for name, detail in FAILURES:
        print(f"  \u274c {name}")
        if detail:
            print(f"       {detail}")
shutil.rmtree(WORK, ignore_errors=True)
sys.exit(1 if FAIL else 0)
