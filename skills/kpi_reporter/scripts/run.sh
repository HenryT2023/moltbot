#!/bin/bash
# KPI Reporter - Moltbot 集成脚本
# 用法: ./scripts/run.sh [options]
#
# 示例:
#   ./scripts/run.sh --time_window yesterday --dry_run
#   ./scripts/run.sh -t last_week -c "#growth"

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(dirname "$SCRIPT_DIR")"

cd "$SKILL_DIR"

# 检查依赖
if ! command -v node &> /dev/null; then
    echo "错误: 需要安装 Node.js" >&2
    exit 1
fi

if ! command -v python3 &> /dev/null; then
    echo "错误: 需要安装 Python3" >&2
    exit 1
fi

# 检查 node_modules
if [ ! -d "node_modules" ]; then
    echo "安装 Node.js 依赖..."
    npm install --silent
fi

# 运行
exec npx tsx src/index.ts "$@"
