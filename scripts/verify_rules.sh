#!/bin/bash
# 龙虾选股系统 — 规则一致性校验脚本
# 用于检查各任务是否读取了最新规则文件
# 修复：2026-05-19 修正所有文件路径（文件已从 memory/ 迁移到 trading/ 或工作区根目录）

set -e

echo "========================================="
echo "  龙虾选股系统 — 规则一致性校验"
echo "========================================="
echo ""

WORKSPACE="$HOME/.qclaw/workspace-1gwpiwf3hr163jz5"
MEMORY="$WORKSPACE/memory"
TRADING="$WORKSPACE/trading"
SCRIPTS="$WORKSPACE/scripts"

ERRORS=0
WARNINGS=0

# ============================================
# 检查1：核心规则文件是否存在（修正后路径）
# ============================================
echo "【检查1】核心规则文件是否存在..."
echo ""

check_file() {
    local file=$1
    local desc=$2
    if [ -f "$file" ]; then
        size=$(wc -c < "$file")
        echo "✅ $desc: $(basename $file) (${size}字节)"
        return 0
    else
        echo "❌ $desc: $(basename $file) 不存在（路径: $file）"
        ERRORS=$((ERRORS + 1))
        return 1
    fi
}

# 修正后的路径检查
check_file "$WORKSPACE/lobster-rules.md" "硬约束规则(lobster-rules.md)"
check_file "$TRADING/产业逻辑框架.md" "产业图谱(产业逻辑框架.md)"
check_file "$TRADING/复盘模板.md" "复盘模板(复盘模板.md)"
check_file "$TRADING/选股历史.md" "选股历史(选股历史.md)"
check_file "$TRADING/heartbeat-rules-full.md" "心跳规则(heartbeat-rules-full.md)"
check_file "$WORKSPACE/HEARTBEAT.md" "心跳规则（精简版）"

echo ""

# ============================================
# 检查2：CRON任务文件是否引用了最新规则
# ============================================
echo "【检查2】CRON任务是否引用最新规则..."
echo ""

check_cron_task() {
    local file=$1
    local task_name=$2
    
    if [ ! -f "$file" ]; then
        echo "❌ $task_name: 文件不存在（路径: $file）"
        ERRORS=$((ERRORS + 1))
        return 1
    fi
    
    local size=$(wc -c < "$file")
    
    # 检查是否引用 lobster-rules.md（在根目录）
    local count=$(grep -c "lobster-rules.md" "$file" 2>/dev/null || echo "0")
    if [ "$count" -gt 0 ] 2>/dev/null; then
        echo "✅ $task_name: 已引用 lobster-rules.md ($count处，${size}字节)"
    else
        echo "⚠️  $task_name: 未引用 lobster-rules.md (${size}字节)"
        WARNINGS=$((WARNINGS + 1))
    fi
}

# cron任务文件实际在 scripts/cron-tasks/ 目录
check_cron_task "$SCRIPTS/cron-tasks/CRON_PREMARKET_TASK.md" "盘前选股(v4硬脚本,无需引用rules)"
check_cron_task "$SCRIPTS/cron-tasks/CRON_BID_FULL_PIPELINE.md" "竞价选股(v9硬脚本,无需引用rules)"
check_cron_task "$SCRIPTS/cron-tasks/CRON_INTRADAY_PATROL_TASK.md" "盘中巡检(买卖点监控)"
check_cron_task "$SCRIPTS/cron-tasks/CRON_MIDDAY_TASK.md" "午间复盘"
check_cron_task "$SCRIPTS/cron-tasks/CRON_CLOSING_COMPREHENSIVE.md" "收盘综合任务"
check_cron_task "$SCRIPTS/cron-tasks/CRON_DAILY_EVOLUTION_TASK.md" "每日进化"

echo ""

# ============================================
# 检查3：产业图谱日期是否最新
# ============================================
echo "【检查3】产业图谱日期是否最新..."
echo ""

if [ -f "$TRADING/产业逻辑框架.md" ]; then
    # 提取日期（假设格式：最后更新：YYYY-MM-DD）
    date_in_file=$(grep -oE "最后更新：[0-9]{4}-[0-9]{2}-[0-9]{2}" "$TRADING/产业逻辑框架.md" | grep -oE "[0-9]{4}-[0-9]{2}-[0-9]{2}" || echo "未找到日期")
    today=$(date +%Y-%m-%d)
    
    if [ "$date_in_file" = "$today" ]; then
        echo "✅ 产业图谱日期: $date_in_file（今天）"
    elif [ "$date_in_file" = "未找到日期" ]; then
        echo "⚠️  产业图谱未标注日期"
        WARNINGS=$((WARNINGS + 1))
    else
        echo "⚠️  产业图谱日期: $date_in_file（非今天，建议更新）"
        WARNINGS=$((WARNINGS + 1))
    fi
else
    echo "❌ 产业图谱文件不存在"
    ERRORS=$((ERRORS + 1))
fi

echo ""

# ============================================
# 检查4：lobster-rules.md文件大小是否正常
# ============================================
echo "【检查4】规则文件大小是否正常..."
echo ""

if [ -f "$WORKSPACE/lobster-rules.md" ]; then
    size=$(wc -c < "$WORKSPACE/lobster-rules.md")
    
    if [ "$size" -lt 10000 ]; then
        echo "⚠️  lobster-rules.md 过小 (${size}字节 < 10KB)"
        echo "    可能是旧版本或文件不完整"
        WARNINGS=$((WARNINGS + 1))
    elif [ "$size" -gt 20000 ]; then
        echo "⚠️  lobster-rules.md 过大 (${size}字节 > 20KB)"
        echo "    可能包含了不必要的内容"
        WARNINGS=$((WARNINGS + 1))
    else
        echo "✅ lobster-rules.md 大小正常 (${size}字节)"
    fi
else
    echo "❌ lobster-rules.md 不存在"
    ERRORS=$((ERRORS + 1))
fi

# 检查版本号一致性
if [ -f "$WORKSPACE/lobster-rules.md" ]; then
    header_version=$(grep -m1 "v[0-9]\.[0-9]" "$WORKSPACE/lobster-rules.md" | grep -oE "v[0-9]\.[0-9]" || echo "未找到")
    content_version=$(grep -m1 "v[0-9]\.[0-9].*新增" "$WORKSPACE/lobster-rules.md" | grep -oE "v[0-9]\.[0-9]" || echo "未找到")
    
    if [ "$header_version" != "未找到" ] && [ "$content_version" != "未找到" ]; then
        if [ "$header_version" != "$content_version" ]; then
            echo "⚠️  版本号不一致：文件头=$header_version，内容=$content_version"
            echo "    建议统一为 $content_version"
            WARNINGS=$((WARNINGS + 1))
        else
            echo "✅ 版本号一致: $header_version"
        fi
    fi
fi

echo ""

# ============================================
# 检查5：Python过滤脚本是否存在
# ============================================
echo "【检查5】Python过滤脚本是否存在..."
echo ""

check_file "$SCRIPTS/lobster_bid_filter_v2.py" "竞价过滤脚本(lobster_bid_filter_v2.py)"
check_file "$SCRIPTS/lobster_premarket_engine.py" "盘前选股引擎(lobster_premarket_engine.py)"
check_file "$SCRIPTS/scoring_calculator.py" "打分计算器(scoring_calculator.py)"

echo ""

# ============================================
# 检查6：数据传递文件是否存在
# ============================================
echo "【检查6】数据传递文件是否存在..."
echo ""

if [ -f "/tmp/lobster_premarket_candidates.json" ]; then
    size=$(wc -c < "/tmp/lobster_premarket_candidates.json")
    echo "✅ 盘前候选池JSON存在 (${size}字节)"
    
    # 检查日期是否为今天
    date_in_json=$(python3 -c "import json; print(json.load(open('/tmp/lobster_premarket_candidates.json'))['date'])" 2>/dev/null || echo "无法解析")
    today=$(date +%Y-%m-%d)
    
    if [ "$date_in_json" = "$today" ]; then
        echo "✅ 盘前候选池日期: $date_in_json（今天）"
    else
        echo "⚠️  盘前候选池日期: $date_in_json（非今天）"
        WARNINGS=$((WARNINGS + 1))
    fi
else
    echo "ℹ️  盘前候选池JSON不存在（可能非交易时段或未执行盘前选股）"
fi

if [ -f "/tmp/lobster_bid_result.json" ]; then
    size=$(wc -c < "/tmp/lobster_bid_result.json")
    echo "✅ 竞价结果JSON存在 (${size}字节)"
else
    echo "ℹ️  竞价结果JSON不存在（可能非交易时段或未执行竞价选股）"
fi

echo ""

# ============================================
# 检查7：最近日志日期
# ============================================
echo "【检查7】最近日志日期..."
echo ""

today=$(date +%Y-%m-%d)
yesterday=$(date -v-1d +%Y-%m-%d 2>/dev/null || date -d "1 day ago" +%Y-%m-%d)

if [ -f "$MEMORY/$today.md" ]; then
    echo "✅ 今日日志存在: $today.md"
elif [ -f "$MEMORY/$yesterday.md" ]; then
    echo "ℹ️  今日日志不存在，昨日日志存在: $yesterday.md"
else
    echo "⚠️  今日和昨日日志都不存在"
    WARNINGS=$((WARNINGS + 1))
fi

echo ""

# ============================================
# 检查8：HEARTBEAT.md 路径引用是否正确
# ============================================
echo "【检查8】HEARTBEAT.md 路径引用是否正确..."
echo ""

if [ -f "$WORKSPACE/HEARTBEAT.md" ]; then
    wrong_ref=$(grep -c "memory/heartbeat-rules-full.md" "$WORKSPACE/HEARTBEAT.md" 2>/dev/null || echo "0")
    if [ "$wrong_ref" -gt 0 ] 2>/dev/null; then
        echo "⚠️  HEARTBEAT.md 包含错误路径引用: memory/heartbeat-rules-full.md（应为 trading/heartbeat-rules-full.md）"
        WARNINGS=$((WARNINGS + 1))
    else
        echo "✅ HEARTBEAT.md 路径引用正确"
    fi
else
    echo "❌ HEARTBEAT.md 不存在"
    ERRORS=$((ERRORS + 1))
fi

echo ""

# ============================================
# 检查9：trading-state.json 是否存在
# ============================================
echo "【检查9】trading-state.json 是否存在..."
echo ""

check_file "$TRADING/trading-state.json" "交易状态(trading-state.json)"

echo ""

# ============================================
# 汇总
# ============================================
echo "========================================="
echo "  校验完成"
echo "========================================="
echo ""
echo "❌ 错误: $ERRORS 个"
echo "⚠️  警告: $WARNINGS 个"
echo ""

if [ "$ERRORS" -gt 0 ]; then
    echo "🚨 存在严重错误，请立即修复！"
    exit 1
elif [ "$WARNINGS" -gt 3 ]; then
    echo "⚠️  警告较多，建议检查"
    exit 2
else
    echo "✅ 规则一致性正常"
    exit 0
fi
