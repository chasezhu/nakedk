#!/usr/bin/env bash
# 裸K战法终端 · 启动脚本
set -euo pipefail

cd "$(dirname "$0")"

PORT="${NAKEDK_PORT:-8600}"
PY="${NAKEDK_PYTHON:-python3}"

case "${1:-start}" in
  start)
    echo "→ 裸K战法终端  http://127.0.0.1:${PORT}"
    exec "$PY" server.py
    ;;
  bg)
    mkdir -p .run
    # 端口预检：重复启动时 uvicorn 只会抛 'address already in use'，
    # 容易被误读成代码问题（本会话踩过一次）。这里先说清楚。
    if curl -s -m 3 "http://127.0.0.1:${PORT}/api/health" >/dev/null 2>&1; then
      echo "→ 端口 ${PORT} 已有服务在跑，不重复启动。"
      echo "  要重启: ./run.sh stop && ./run.sh bg"
      curl -s "http://127.0.0.1:${PORT}/api/health"; echo
      exit 0
    fi
    nohup "$PY" server.py > .run/server.log 2>&1 &
    echo $! > .run/server.pid
    echo "→ 已后台启动 PID $(cat .run/server.pid)，日志 .run/server.log"
    sleep 2
    curl -s "http://127.0.0.1:${PORT}/api/health" && echo
    ;;
  stop)
    if [ -f .run/server.pid ]; then
      kill "$(cat .run/server.pid)" 2>/dev/null || true
      rm -f .run/server.pid
      echo "→ 已停止"
    else
      echo "→ 未找到 .run/server.pid"
    fi
    ;;
  smoke)
    "$PY" dev/smoke.py "${2:-300768}"
    ;;
  ab)
    "$PY" dev/ab_ice.py "${2:-300768}" "${3:-}"
    ;;
  backfill)
    shift
    "$PY" dev/backfill.py "$@"
    ;;
  contract)
    "$PY" dev/contract.py
    ;;
  purge)
    shift
    "$PY" dev/purge_intraday.py "$@"
    ;;
  *)
    cat <<'USAGE'
用法: ./run.sh <命令> [参数]

  start              前台启动服务
  bg                 后台启动服务（日志 .run/server.log）
  stop               停止后台服务
  smoke [代码]       引擎自检，打印五模块全部字段（默认 300768）
  ab <代码> [日期]   冰线优先级1 正序(v3) vs 倒序(本版) A/B 对比
  backfill [--watchlist] [--days N] [代码...]
                     历史回算并落盘，让模块六立即可用
  contract           输出契约回归（10 标的 × 全字段断言）
  purge [--dry-run]  清理"当日K线未完成"时写入的脏历史
USAGE
    exit 1
    ;;
esac
