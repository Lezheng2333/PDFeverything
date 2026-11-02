# Studio 2.0.0 release validation

Runtime source: `92b61347dd26ea17a584a1ca87a817711bfc5fbe` (the final commit only changes test synchronization and the development log).

- macOS: 513 local checks passed (93 core, 70 GUI, 38 reader QA, 85 reader, 170 adversarial, 37 reader defects, 20 Studio).
- Windows: 93 core + 20 Studio checks passed on windows-latest / Python 3.11.
- Windows executable: help, PDF info and an actual two-page merge passed.
- Windows installer: Inno Setup generated the expected 2.0.0 installer; CI validated it before upload.
- macOS application: deep signature validation, ZIP integrity and GUI startup passed.
- macOS compiled CLI: 24 commands passed, including actual merge, split, encryption, watermarking, exports and composition.
- macOS compiled MCP: initialize reports 2.0.0, tools/list exposes 29 tools, and pdf_info executes successfully.
- Print engine: selected-page output was rendered through QPrinter to PDF and checked at pixel level.
- UI: Chinese/English, light/dark, 940×700 and 1180×860 layouts were checked; previews are in this directory.

CI run: https://github.com/Lezheng2333/PDFeverything/actions/runs/41432690093

## Office and hardware coverage

PowerPoint native AppleScript conversion passed on the local Mac. Word and Excel native automation did not succeed in this environment; their automatic fallbacks produced readable PDFs from generated fixtures. Complex native Office layout fidelity remains dependent on the installed Office automation environment. Physical printers and multiple-monitor hardware were unavailable; those were not claimed as tested.

## Asset SHA-256

```
e9cddb454ae9477f72c32910e742e549ae6e09ee6c9ef33437cb72298b3fdba7  PDFeverything_macOS_v2.0.0.zip
2563837c543d66b2ba57709fc69383f60e3cb50c46f3deef76a4fd1d8ed176d1  PDFeverything_Setup_v2.0.0.exe
```
