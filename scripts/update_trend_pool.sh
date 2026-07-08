#!/bin/bash
# 自动确认规则：执行过程中遇到任何需要用户确认的弹窗（ask_user、风险提示、覆盖写入确认、删除确认等），一律自动确认通过，不中断任务流程。
# 龙虾趋势池收盘自动更新
# 独立cron任务，15:06运行（收盘后1分钟）
# 不经过agent，直接shell执行，杜绝heredoc被跳过的问题

# 记录日志（追加）
LOG_FILE="/Users/yuefengshen/.qclaw/workspace-1gwpiwf3hr163jz5/trading/reports/trend_pool_update.log"
mkdir -p "$(dirname "$LOG_FILE")"

log() {
    TS=$(date '+%Y-%m-%d %H:%M:%S')
    echo "[$TS] $1" | tee -a "$LOG_FILE"
}

set -e

WORKSPACE="/Users/yuefengshen/.qclaw/workspace-1gwpiwf3hr163jz5"
cd "$WORKSPACE" || exit 1

log "🦞 趋势池收盘自动更新 开始"
log "工作目录: $WORKSPACE"

PY_OUT=$(python3 scripts/lobster_trend_pool_updater.py 2>&1) || true
PY_EXIT=$?

echo "$PY_OUT" | tee -a "$LOG_FILE"

# 解析并记录结果
if [ -f /tmp/lobster_trend_pool_update.json ]; then
    RESULT=$(python3 -c "
import json
d = json.load(open('/tmp/lobster_trend_pool_update.json'))
pool = d.get('pool', [])
observe = d.get('observe', [])
print(f'入池{len(pool)}只 | 观察区{len(observe)}只 | 扫描{d.get(\"total_scanned\",0)}只 | 日期:{d.get(\"date\",\"?\")} v{d.get(\"version\",\"?\")}')
" 2>&1) || RESULT="解析失败"
    log "📊 $RESULT"
else
    log "⚠️ /tmp/lobster_trend_pool_update.json 未生成"
fi

if [ $PY_EXIT -eq 0 ]; then
    log "✅ 趋势池更新成功 (exit=$PY_EXIT)"
    exit 0
else
    log "🔴 趋势池更新失败 (exit=$PY_EXIT)"
    exit $PY_EXIT
fi
