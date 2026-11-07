#!/usr/bin/env bash
# 本地起一个静态服务打开 Allure 报告。
#
# 为什么必须有这一步：Allure 报告是 SPA，靠 XHR 读取 data/*.json。
# Chrome 会拦截 file:// 页面对本地文件的 XHR，直接双击 uireport.html
# 会永远停在 "Loading..."（已实测：file:// 下 7 个 widget 全是 Loading，
# http:// 下正常显示 154 test cases）。所以报告只能经 HTTP 打开。
#
# 用法：
#   bash tools/serve_report.sh          # 默认 8899 端口
#   bash tools/serve_report.sh 9000     # 指定端口
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DIR="$ROOT/onlineexam_ui_autotest/report/allure-report"
PORT="${1:-8899}"

if [ ! -f "$DIR/uireport.html" ]; then
  echo "[FAIL] 找不到报告入口 $DIR/uireport.html（先跑 bash tools/gen_report.sh）" >&2
  exit 1
fi

echo "报告地址: http://127.0.0.1:$PORT/uireport.html"
echo "（Ctrl+C 停止）"
cd "$DIR"
exec python -m http.server "$PORT" --bind 127.0.0.1
