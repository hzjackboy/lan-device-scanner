#!/usr/bin/env bash
# 一键启动局域网设备扫描服务
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"

PY="${PYTHON:-}"
if [ -z "$PY" ]; then
  if command -v python3 >/dev/null 2>&1; then
    PY=python3
  else
    echo "找不到 python3，请先安装 Python 3.9+" >&2
    exit 1
  fi
fi

exec "$PY" server.py "$@"
