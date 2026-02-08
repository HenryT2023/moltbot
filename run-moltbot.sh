#!/bin/bash
# Moltbot 自动重启脚本
# 用法: ./run-moltbot.sh [--dev]

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

MODE=""
if [[ "$1" == "--dev" ]]; then
    MODE="--dev"
fi

RESTART_DELAY=5  # 重启前等待秒数
MAX_RAPID_RESTARTS=5  # 快速重启次数上限
RAPID_RESTART_WINDOW=60  # 快速重启检测窗口（秒）

restart_times=()

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1"
}

cleanup() {
    log "收到退出信号，正在停止..."
    exit 0
}

trap cleanup SIGINT SIGTERM

check_rapid_restart() {
    local now=$(date +%s)
    local cutoff=$((now - RAPID_RESTART_WINDOW))
    
    # 过滤掉过期的重启时间
    local new_times=()
    for t in "${restart_times[@]}"; do
        if [[ $t -ge $cutoff ]]; then
            new_times+=("$t")
        fi
    done
    restart_times=("${new_times[@]}")
    
    # 添加当前时间
    restart_times+=("$now")
    
    # 检查是否超过阈值
    if [[ ${#restart_times[@]} -ge $MAX_RAPID_RESTARTS ]]; then
        log "⚠️  检测到快速重启循环（${RAPID_RESTART_WINDOW}秒内重启${#restart_times[@]}次）"
        log "暂停 60 秒后继续..."
        sleep 60
        restart_times=()
    fi
}

log "🦞 Moltbot 自动重启脚本启动"
log "模式: ${MODE:-production}"
log "按 Ctrl+C 停止"

while true; do
    log "启动 Moltbot..."
    
    if node start-with-proxy.mjs $MODE gateway run; then
        log "Moltbot 正常退出"
    else
        EXIT_CODE=$?
        log "⚠️  Moltbot 异常退出 (exit code: $EXIT_CODE)"
    fi
    
    check_rapid_restart
    
    log "将在 ${RESTART_DELAY} 秒后重启..."
    sleep $RESTART_DELAY
done
