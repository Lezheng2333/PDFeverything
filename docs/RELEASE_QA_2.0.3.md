# PDFeverything 2.0.3 验收记录 — Office 自动化 TCC 授权

日期：2026-11-09
范围：[PR #2](https://github.com/Lezheng2333/PDFeverything/pull/2) 报告的「合并 Office 文件卡死」

## 1. 问题复核

PR 描述：macOS 第一次向 Word / PowerPoint / Excel 发送 Apple Event 会弹出「自动化」授权框，
`osascript` 会阻塞到用户响应；如果没人点，旧代码要等满 300 秒才回退。

2.0.2 的代码确认仍然存在这条路径：

- `core/converters.py: _applescript_convert(..., timeout=300)`，Word / PPT / Excel 三处调用都传 300；
- 转换前没有 TCC 探测，CLI / MCP 进程里 `_office_cache` 为 `None` → `_office_ready()` 返回 True →
  直接进入 300 秒的 `osascript`；
- 更糟的是 GUI 启动探测用的是 `tell application X to get version`（真正的 Apple Event）：
  首次启动就会启动 Office 并弹三个授权框，每个最多阻塞 10 秒。

结论：**问题仍然存在**，PR 的方向正确。

## 2. 修复（未直接合并 PR #2）

PR 的实现有三处不能直接并入：`script.format(input_path=...)` 把路径拼回脚本（重新引入
AppleScript 注入，v2.0.1 已修）、`LSMinimumSystemVersion` 改回 14.0（会放弃 macOS 13）、
新增的 `build_macos.sh` 与 2.0.2 的 `build_macos.py` 重复且版本停留在 1.4.2。
因此按同样的思路在 2.0.2 上重写：

- **6 秒 TCC 探测**：`_automation_granted(app)` 用 `tell application X to get version` 做最短探测，
  结果缓存 30 秒（授权成功永久有效）；转换前调用，失败立即回退内置渲染。
- **90 秒转换上限**：授权已通过后 Office 自身卡住（文档恢复、模态框）不再拖 5 分钟。
- **静默可用性探测**：`_check_office_macos()` 改用 LaunchServices（`id of app "Microsoft Word"`），
  不启动 Office、不触发 TCC；GUI 启动探测从最多 30 秒降到约 0.1 秒。
- **路径安全不变**：仍走 `osascript -e script -- path path`，未采纳 PR 的 format 方案。

## 3. 验证

八套回归全绿，共 **566 项**（`test_core` 101 / `test_macos_compat` 40 / `test_gui` 70 /
`qa_reader` 38 / `test_reader` 85 / `qa_adversarial` 170 / `qa_reader_defects` 37 /
`test_studio` 25）。

新增 4 项 TCC 回归（`tests/test_core.py`）：

| 断言 | 结果 |
|---|---|
| 探测超时 → 只调用一次 osascript，直接返回 False | ✅ |
| 权限被拒 → 结果缓存，后续转换不再重复探测 | ✅ |
| 已授权 → 探测 + 真正转换两次调用，输出校验通过 | ✅ |
| `_applescript_convert` 默认超时 = 90 秒 | ✅ |
| 路径仍以 argv 传入（注入回归） | ✅ |

真实环境（本机已授权）：

```text
osascript 'tell application "Microsoft Word" to get version'   → 0.07 s
WordConverter 转换 docx                                         → 1.70 s，输出 3.4 MB
冻结包 mixed-merge docx → pdf                                   → 0.49 s，1 页
```

构建审计（`python -m core.compat`）：145 个 Mach-O，声明/实际最低系统 13.0，外部路径引用 0，`RESULT: OK`。

## 4. 产物

| 项 | 值 |
|---|---|
| `PDFeverything_macOS_v2.0.3.zip` | 72,563,769 bytes |
| SHA-256 | `eedcdc3d9c108f59a43c5870c2df5445493a594cfd532070c1f60714959c683d` |
| 架构 / 最低系统 | arm64 / macOS 13.0 |
| 签名 | ad-hoc（未公证） |

## 5. 已知边界

- **无法在不打扰用户的前提下复现「弹窗无人响应」**：本机已经授权，`tccutil reset AppleEvents`
  会重置所有 App 的自动化授权，因此未使用；该分支由 mock 超时测试覆盖。
- 90 秒是经验上限：超大文档（数百页）可能不够；失败会回退内置渲染并保留可读内容，
  而不是无限等待。
- 授权结果缓存 30 秒：用户如果在弹窗出现后超过 30 秒才点「允许」，本次批量可能仍走回退，
  下一次转换会重新探测并走 Office。
- Windows 的 COM 超时保持 300 秒（不涉及 TCC），本次未改。
