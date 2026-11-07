#!/usr/bin/env bash
# 生成 Allure 静态报告，并把入口重命名为 uireport.html。
#
# 为什么要有这一步：Allure CLI 每次都写死 index.html，而本项目要求入口叫
# uireport.html（避免与其他静态站点默认入口混淆）。手工改名容易被下一次
# 生成覆盖，因此统一走脚本。
#
# 实现说明：真正的逻辑在 `onlineexam_ui_autotest/common/report_builder.py`，
# 本脚本只是挑一个可用的 Python 去调它。**故意不在 bash 里再抄一遍**——
# 早先这里有一套独立的 sed/cat 实现，`Run=` 硬编码成 "FULL-09"，于是
# 手工跑 .sh 得到的报告首页永远显示同一轮，而 conftest 自动生成（走 Python）
# 却是动态的。两份实现=两种口径，最终一定会有人被误导。
#
# 用法：
#   bash tools/gen_report.sh            # 用 report/allure-results 生成
#   bash tools/gen_report.sh --open     # 生成后额外打印入口绝对路径
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"

PY=""
for cand in "/d/python/python.exe" "$ROOT/../python/python.exe" "python" "python3"; do
  if command -v "$cand" >/dev/null 2>&1 || [ -x "$cand" ]; then PY="$cand"; break; fi
done
if [ -z "$PY" ]; then
  echo "[FAIL] 找不到 Python（本脚本依赖它调用 common/report_builder.py）" >&2
  exit 1
fi

"$PY" "$ROOT/tools/gen_report.py"
if [ "${1:-}" = "--open" ]; then
  echo "$ROOT/onlineexam_ui_autotest/report/allure-report/uireport.html"
fi
