# Studio 2.0.0 release validation

Release: [PDFeverything v2.0.0](https://github.com/Lezheng2333/PDFeverything/releases/tag/v2.0.0) (published 2026-11-02)

Runtime source: `92b61347dd26ea17a584a1ca87a817711bfc5fbe` — the commit tagged `v2.0.0`.
Commits after the tag (`8c4fd9c`, `c8dd384`) only update documentation.

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

## Artifacts

| Asset | Size (bytes) | SHA-256 |
|---|---:|---|
| [`PDFeverything_macOS_v2.0.0.zip`](https://github.com/Lezheng2333/PDFeverything/releases/download/v2.0.0/PDFeverything_macOS_v2.0.0.zip) | 73,147,149 | `e9cddb454ae9477f72c32910e742e549ae6e09ee6c9ef33437cb72298b3fdba7` |
| [`PDFeverything_Setup_v2.0.0.exe`](https://github.com/Lezheng2333/PDFeverything/releases/download/v2.0.0/PDFeverything_Setup_v2.0.0.exe) | 97,672,899 | `2563837c543d66b2ba57709fc69383f60e3cb50c46f3deef76a4fd1d8ed176d1` |
| [`SHA256SUMS.txt`](https://github.com/Lezheng2333/PDFeverything/releases/download/v2.0.0/SHA256SUMS.txt) | 194 | `85b09a25353fa48749ea86baa615f7921c15b10abd77a64f204bf706b2ba357d` |

## Office and hardware coverage

PowerPoint native AppleScript conversion passed on the local Mac. Word and Excel native automation did not succeed in this environment; their automatic fallbacks produced readable PDFs from generated fixtures. Complex native Office layout fidelity remains dependent on the installed Office automation environment. Legacy binary formats (`.doc`, `.ppt`, `.xls`, `.rtf`) require native Office automation; the pure-Python fallback covers `.docx`, `.pptx` and `.xlsx`. Physical printers and multiple-monitor hardware were unavailable; those were not claimed as tested.

## 中文摘要

- macOS 本地 **513 项**回归全部通过（93 核心 + 70 GUI + 38 阅读器 QA + 85 阅读器综合 + 170 对抗 + 37 阅读器缺陷 + 20 Studio）。
- Windows CI（windows-latest / Python 3.11）通过 **93 项核心 + 20 项 Studio**，并验证冻结 exe 的帮助、PDF info 与实际合并。
- 安装包由 Inno Setup 生成；macOS 应用通过深度签名、ZIP 完整性与 GUI 启动检查。
- 编译后的 CLI 通过 24 条命令；MCP `initialize` 报告 2.0.0，`tools/list` 返回 29 个工具。
- 验收边界：物理打印机、多显示器及本机 Word / Excel 原生自动化未覆盖；Word / Excel 自动降级输出已验证可读。旧版二进制格式（`.doc`、`.ppt`、`.xls`、`.rtf`）依赖原生 Office 自动化，纯 Python 回退覆盖 `.docx`、`.pptx`、`.xlsx`。
