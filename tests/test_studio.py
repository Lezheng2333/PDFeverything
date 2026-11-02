"""Studio workflow regressions. Uses real PDFs and isolated user preferences.

Run: QT_QPA_PLATFORM=offscreen .venv/bin/python tests/test_studio.py
"""

import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import fitz
from PyQt6.QtCore import QSettings, Qt
from PyQt6.QtGui import QAction, QCloseEvent
from PyQt6.QtWidgets import QApplication, QFileDialog, QListWidget

SETTINGS = tempfile.TemporaryDirectory(prefix="pdfeverything-studio-settings-")
QSettings.setDefaultFormat(QSettings.Format.IniFormat)
QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, SETTINGS.name)
app = QApplication.instance() or QApplication([])
app.setStyle("Fusion")

from core.utils import set_office_cache
from core.pdf_ops import PdfOperator
from gui.main_window import MainWindow
from gui.workspace import CommandPalette, TOOLS
import gui.main_window as main_module


class StudioTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix="pdfeverything-studio-")
        cls.root = Path(cls.tmp.name).resolve()
        cls.pdfs = []
        for name in ("report", "appendix", "notes"):
            path = cls.root / (name + ".pdf")
            doc = fitz.open()
            for i in range(2):
                page = doc.new_page(); page.insert_text((60, 80), f"{name} page {i + 1}")
            doc.save(path); doc.close(); cls.pdfs.append(path)

    def setUp(self):
        set_office_cache({"word": False, "powerpoint": False, "excel": False})
        self.window = MainWindow(); self.window.show(); app.processEvents()
        self.window._show_message = lambda *args: None

    def tearDown(self):
        self.window.reader._unsaved_edits = False
        self.window.reader.close_document()
        self.window.close(); self.window.deleteLater(); app.processEvents()

    def test_tool_search_and_categories(self):
        library = self.window.tool_library
        library.search.setText("Word")
        self.assertEqual(sum(not b.isHidden() for b, _ in library.cards), 1)
        library.search.clear(); library.set_category("secure")
        self.assertEqual(sum(not b.isHidden() for b, _ in library.cards), 4)
        library.search.setText("不存在的工具")
        self.assertTrue(library.empty.isVisibleTo(library))
        self.assertTrue(all(hasattr(self.window, t[1]) for t in TOOLS))

    def test_command_dispatch_and_bilingual_search(self):
        palette = CommandPalette(self.window)
        palette.search.setText("压缩")
        self.assertEqual(palette.results.count(), 1)
        self.assertEqual(palette.results.item(0).data(Qt.ItemDataRole.UserRole), "act_compress")
        called = []; action = QAction(self.window); action.triggered.connect(lambda: called.append(True))
        with patch.object(self.window, "act_compress", action):
            palette.run_current(); app.processEvents()
        self.assertEqual(called, [True])

    def test_selected_pdfs_take_priority(self):
        self.window.file_list.add_files(self.pdfs)
        self.window.file_list.list_widget.setCurrentRow(1)
        self.assertEqual(self.window._pick_input_files(), [self.pdfs[1]])
        self.window.file_list.list_widget.clearSelection()
        self.assertEqual(self.window._pick_input_files(), self.pdfs)

    def test_compression_mode_reaches_single_and_batch_engine(self):
        with patch.object(main_module, "CompressDialog") as dialog, \
             patch.object(self.window, "_get_output_path", return_value=self.root / "compressed.pdf"), \
             patch.object(self.window, "_run_worker") as run, \
             patch.object(self.window, "_run_batch") as batch:
            dialog.return_value.exec.return_value = 1
            for index, mode in enumerate(("lossless", "medium", "max")):
                dialog.return_value.get_mode.return_value = index
                with patch.object(self.window, "_pick_input_files", return_value=self.pdfs[:1]):
                    self.window._on_compress_clicked()
                    self.assertEqual(run.call_args.args[-1], mode)
                with patch.object(self.window, "_pick_input_files", return_value=self.pdfs[:2]):
                    self.window._on_compress_clicked()
                    self.assertEqual(batch.call_args.args[-1], mode)

    def test_cancelled_save_keeps_reader_and_window_open(self):
        reader = self.window.reader; reader.open_pdf(self.pdfs[0]); reader._unsaved_edits = True
        with patch.object(reader, "_prompt_save_changes", return_value="save_as"), \
             patch.object(QFileDialog, "getSaveFileName", return_value=("", "")):
            reader._on_close(); self.assertTrue(reader.has_document())
            event = QCloseEvent(); self.window.closeEvent(event)
            self.assertFalse(event.isAccepted()); self.assertTrue(reader._unsaved_edits)

    def test_switch_cancel_and_invalid_open_preserve_document(self):
        reader = self.window.reader; reader.open_pdf(self.pdfs[0]); original = reader.doc
        reader._unsaved_edits = True
        with patch.object(reader, "_prompt_save_changes", return_value="cancel"):
            self.assertFalse(reader.open_pdf(self.pdfs[1]))
        self.assertIs(reader.doc, original)
        self.assertFalse(reader.open_pdf(self.root / "missing.pdf"))
        self.assertIs(reader.doc, original); self.assertFalse(original.is_closed)
        reader._unsaved_edits = False; reader.open_pdf(self.pdfs[1])
        self.assertTrue(original.is_closed)

    def test_recent_documents_are_bounded_and_deduplicated(self):
        reader = self.window.reader
        for path in self.pdfs + self.pdfs: reader._record_recent(path)
        self.assertEqual(reader._recent_documents(), list(reversed(self.pdfs)))
        reader._clear_recent(); self.assertEqual(reader._recent_documents(), [])

    def test_internal_drop_uses_native_reordering(self):
        from unittest.mock import Mock
        event = Mock(); event.mimeData.return_value.hasUrls.return_value = False
        with patch.object(QListWidget, "dropEvent") as native_drop:
            self.window.file_list._drop_event(event)
            native_drop.assert_called_once_with(self.window.file_list.list_widget, event)

    def test_canonical_file_paths_are_deduplicated(self):
        self.window.file_list.add_files([self.pdfs[0], self.pdfs[0].parent / "." / self.pdfs[0].name])
        self.assertEqual(self.window.file_list.count(), 1)

    def test_output_filename_is_preserved(self):
        custom = self.root / "my-project.pdf"
        self.window.output_path_edit.setText(str(custom))
        with patch.object(QFileDialog, "getSaveFileName", return_value=(str(custom), "")) as choose:
            self.assertEqual(self.window._get_output_path("merged.pdf"), custom)
            self.assertEqual(choose.call_args.args[2], str(custom))

    def test_real_merge_exposes_output_and_reader(self):
        output = self.root / "merged.pdf"
        self.window._run_worker(PdfOperator.merge, self.pdfs[:2], output)
        deadline = time.monotonic() + 5
        while self.window._worker.isRunning() and time.monotonic() < deadline:
            app.processEvents(); time.sleep(.01)
        app.processEvents()
        self.assertTrue(output.exists()); self.assertEqual(self.window._last_output, output)
        self.assertFalse(self.window.btn_result_open.isHidden())
        self.window._open_last_output()
        self.assertEqual(self.window.reader._total_pages, 4)

    def test_language_and_theme_switch_are_live(self):
        self.window._switch_language("en")
        self.assertEqual(self.window.tabs.tabText(0), "Workspace")
        self.assertEqual(self.window.btn_open.text(), "Open PDF")
        before = app.palette().window().color().name()
        self.window._toggle_theme()
        self.assertNotEqual(app.palette().window().color().name(), before)
        self.window._toggle_theme(); self.window._switch_language("zh")

    def test_folder_import_and_multi_selection_order(self):
        folder = self.root / "folder"; folder.mkdir(exist_ok=True)
        for name in ("page10.txt", "page2.txt", "ignored.bin"):
            (folder / name).write_text("document")
        self.window.file_list.add_folder(folder)
        self.assertEqual([p.name for p in self.window.file_list.get_file_paths()], ["page2.txt", "page10.txt"])
        self.window.file_list.clear(); self.window.file_list.add_files(self.pdfs)
        queue = self.window.file_list.list_widget
        queue.item(1).setSelected(True); queue.item(2).setSelected(True)
        self.window.file_list._on_move_up()
        self.assertEqual(self.window.file_list.get_file_paths(), self.pdfs[1:] + self.pdfs[:1])
        self.assertEqual(len(queue.selectedItems()), 2)

    def test_batch_output_does_not_overwrite_existing_files(self):
        base = self.window._get_batch_output_path(self.pdfs[0], "safe", self.root)
        base.write_text("keep this")
        next_path = self.window._get_batch_output_path(self.pdfs[0], "safe", self.root)
        self.assertNotEqual(base, next_path); self.assertEqual(base.read_text(), "keep this")

    def test_native_print_engine_outputs_only_selected_page(self):
        from PyQt6.QtPrintSupport import QPrinter
        from gui.printing import print_pages
        doc = fitz.open()
        for color in ((1, 0, 0), (0, 0, 1)):
            page = doc.new_page(); page.draw_rect(page.rect, color=None, fill=color)
        output = self.root / "print-selected.pdf"
        printer = QPrinter(); printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
        printer.setOutputFileName(str(output)); print_pages(doc, [1], printer); doc.close()
        with fitz.open(output) as printed:
            self.assertEqual(len(printed), 1)
            pix = printed[0].get_pixmap()
            rgb = pix.pixel(pix.width // 2, pix.height // 2)
            self.assertGreater(rgb[2], 240); self.assertLess(rgb[0], 20)

    def test_history_is_bounded_and_reopenable(self):
        import json
        for _ in range(35): self.window._record_job(True, self.pdfs[0])
        entries = json.loads(self.window._settings.value("studio_history"))
        self.assertEqual(len(entries), 30); self.assertEqual(entries[0]["output"], str(self.pdfs[0]))
        from gui.workspace import HistoryDialog
        history = HistoryDialog(self.window)
        self.assertEqual(history.items.count(), 30); history.close()

    def test_office_probe_uses_independent_instances(self):
        from unittest.mock import Mock
        from core.utils import _probe_office_com
        client = Mock(); client.DispatchEx.return_value.Version = "16.0"
        self.assertTrue(all(_probe_office_com(client).values()))
        self.assertEqual(client.DispatchEx.call_count, 3)
        client.Dispatch.assert_not_called()
        self.assertEqual(client.DispatchEx.return_value.Quit.call_count, 3)

    def test_portrait_pdf_keeps_aspect_ratio_in_slides(self):
        from pptx import Presentation
        output = self.root / "aspect.pptx"
        PdfOperator.to_ppt(self.pdfs[0], output, dpi=72)
        shape = Presentation(output).slides[0].shapes[0]
        self.assertAlmostEqual(shape.width / shape.height, 595 / 842, places=3)
        self.assertGreater(shape.left, 0)

    def test_word_fallback_wraps_and_preserves_long_paragraphs(self):
        from docx import Document
        from core.converters import WordConverter
        doc = Document(); para = doc.add_paragraph()
        para.add_run("Start "); para.add_run("together ").bold = True
        para.add_run("measured wrapping " * 90 + " END_MARKER")
        source = self.root / "long.docx"; output = self.root / "long.pdf"; doc.save(source)
        WordConverter()._fallback_convert(source, output)
        with fitz.open(output) as pdf:
            text = "".join(page.get_text() for page in pdf)
            self.assertIn("Start together", text); self.assertIn("END_MARKER", text)
            for page in pdf:
                for word in page.get_text("words"):
                    self.assertLessEqual(word[2], page.rect.width - 45)

    def test_office_probe_does_not_block_window_creation(self):
        set_office_cache(None)
        import threading
        entered, release = threading.Event(), threading.Event()
        probe_threads = []
        def slow_probe(**kwargs):
            probe_threads.append(threading.get_ident()); entered.set()
            release.wait(5)
            return {"word": False}
        with patch.object(main_module, "check_office_availability", side_effect=slow_probe):
            other = None
            try:
                other = MainWindow()
                self.assertTrue(entered.wait(1))
                self.assertNotEqual(probe_threads[0], threading.get_ident())
            finally:
                release.set()
                if other is not None:
                    other.close(); other.deleteLater(); app.processEvents()
        set_office_cache({"word": False})


if __name__ == "__main__":
    unittest.main(verbosity=2)
