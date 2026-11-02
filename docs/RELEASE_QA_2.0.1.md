# PDFeverything 2.0.1 release validation

Release: [PDFeverything v2.0.1](https://github.com/Lezheng2333/PDFeverything/releases/tag/v2.0.1) (2026-11-02)

Runtime source: the `v2.0.1` release tag. Final commit hash and Windows CI run are recorded below once the tag is built.

## Local validation (macOS)

- **522 checks passed** across seven suites: 97 core + 70 GUI + 38 reader QA + 85 reader + 170 adversarial + 37 reader defects + 25 Studio.
- **Themes**: forest green / warm cherry / Florence blue, each in light and dark mode; scheme switching, persistence, hero artwork, tool badges and reader grid styles checked offscreen.
- **macOS bundle**: `PDFeverything.app` reports `CFBundleShortVersionString` / `CFBundleVersion` **2.0.1**; `codesign --verify --deep --strict` passed.
- **Frozen CLI**: `--version` reports `PDFeverything v2.0.1`; `-h`, `info` and a real two-page merge passed on the packaged binary.
- **Frozen MCP**: `initialize` reports **2.0.1**, `tools/list` exposes **29** tools; stdout stayed clean JSON-RPC.
- **Security/robustness regressions**: AppleScript path injection, Windows COM independent instance, compressed RGB/gray images, legacy Office clear errors, MCP non-UTF-8 stdout, `pages: "all"`, page-edit journal, encrypted/corrupt inputs, metadata/bookmark preservation and print order.

## Windows validation

- CI run: pending.
- Covered by `.github/workflows/build-windows-installer.yml`: 97 core + 25 Studio checks, PyInstaller onefile build, Inno Setup installer, frozen help/info/merge/encrypt/decrypt smoke tests.

## Artifacts

| Asset | Size (bytes) | SHA-256 |
|---|---:|---|
| [`PDFeverything_macOS_v2.0.1.zip`](https://github.com/Lezheng2333/PDFeverything/releases/download/v2.0.1/PDFeverything_macOS_v2.0.1.zip) | 73,156,388 | `9cfff3d50cd9bfa84302e897739cdfb0ef0a4525ef2b2078f361edc2ac829262` |
| `PDFeverything_Setup_v2.0.1.exe` | pending | pending |
| `SHA256SUMS.txt` | pending | pending |

## Coverage and boundaries

- Legacy binary Office formats (`.doc`, `.rtf`, `.ppt`, `.xls`) still require native Microsoft Office automation; 2.0.1 now gives an actionable message instead of a ZIP/parser error.
- Physical printers, multiple-monitor hardware and Windows Office layout fidelity require the corresponding hardware/software and were not claimed as tested.
- Theme checks are offscreen rendering checks; the three palettes were also inspected through the Qt widget tree (menu, hero, tool badges, reader grid).

## 中文摘要

- macOS 本地 **522 项**回归全部通过（97 核心 + 70 GUI + 38 阅读器 QA + 85 阅读器 + 170 对抗 + 37 阅读器缺陷 + 25 Studio）。
- 三套配色（森林绿 / 暖樱红 / 翡冷翠蓝）均含明暗模式，切换与持久化已验证。
- 冻结后的 macOS app/CLI/MCP 均为 2.0.1；CLI 实跑帮助、info、合并，MCP 报告 2.0.1 与 29 个工具。
- Windows CI 将运行核心 + Studio 套件、构建 exe/安装包，并对冻结 exe 验证 help / info / merge / encrypt / decrypt。
- 旧版 `.doc/.rtf/.ppt/.xls` 仍需原生 Office；2.0.1 改为明确提示。物理打印机、多显示器与 Windows Office 版式未覆盖。
