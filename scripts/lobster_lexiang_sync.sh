#!/bin/bash
# lobster_lexiang_sync.sh — 龙虾系统数据每日同步到腾讯乐享
# 由 cron 每日 02:00 触发
# 依赖: mcporter (乐享 MCP 已配置)

set -euo pipefail

WORKSPACE="/Users/yuefengshen/.qclaw/workspace-1gwpiwf3hr163jz5"
SPACE_ID="1353939a48bc4183bc8340cd28e7d3e7"  # 沈跃峰的个人知识库
DATE=$(date +%Y-%m-%d)
DATE_SHORT=$(date +%m-%d)
LOG_FILE="/tmp/lobster_lexiang_sync_${DATE}.log"

log() {
    echo "[$(date '+%H:%M:%S')] $*" | tee -a "$LOG_FILE"
}

import_doc() {
    local title="$1"
    local file_path="$2"
    
    if [ ! -f "$file_path" ]; then
        log "⚠️  跳过 $title — 文件不存在: $file_path"
        return 1
    fi
    
    # 用 python 一次性完成：读取 + 截断 + 调用 mcporter
    python3 << PYEOF
import subprocess, json, sys

file_path = "$file_path"
title = "$title"
space_id = "$SPACE_ID"

try:
    with open(file_path, 'r', encoding='utf-8') as f:
        text = f.read()
except Exception as e:
    print(f"⚠️  读取失败: {e}")
    sys.exit(1)

if not text.strip():
    print(f"⚠️  跳过 {title} — 内容为空")
    sys.exit(1)

# 截断过长内容
if len(text) > 400000:
    text = text[:400000] + '\n\n...(内容截断)'

# 构建 mcporter 命令
# 把内容写入临时文件避免 shell 转义问题
import tempfile, os
tmp = tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False, encoding='utf-8')
tmp.write(text)
tmp.close()

# 直接用 content 参数传递（mcporter 会自动处理）
cmd = [
    'mcporter', 'call', 'lexiang.entry_import_content',
    f'name={title}',
    'content_type=markdown',
    f'space_id={space_id}',
]

# 通过 stdin 传内容避免 shell 转义
result = subprocess.run(
    cmd,
    input=text,
    capture_output=True,
    text=True,
    timeout=30
)

os.unlink(tmp.name)

if result.returncode == 0:
    try:
        data = json.loads(result.stdout)
        entry_id = data.get('entry', {}).get('id', 'UNKNOWN')
        print(f"✅ {title} → entry_id={entry_id}")
    except:
        print(f"✅ {title} → 已创建 (无法解析ID)")
else:
    print(f"❌ {title} 创建失败: {result.stderr[:200]}")
PYEOF
}

# ===== 主流程 =====
log "🦞 龙虾系统 → 腾讯乐享 每日同步开始 ($DATE)"

# 1. 新闻资讯
log "--- 同步新闻 ---"
import_doc "龙虾-${DATE_SHORT}-新闻资讯" \
    "${WORKSPACE}/trading/news/${DATE}.md" || true

# 2. 催化日历
log "--- 同步催化日历 ---"
import_doc "龙虾-最新-催化日历" \
    "${WORKSPACE}/trading/催化日历.md" || true

# 3. 趋势容量池
log "--- 同步趋势池 ---"
import_doc "龙虾-最新-趋势容量池" \
    "${WORKSPACE}/trading/趋势容量池.md" || true

# 4. 产业图谱
log "--- 同步产业图谱 ---"
import_doc "龙虾-${DATE_SHORT}-产业图谱" \
    "${WORKSPACE}/trading/sector_map_${DATE}.md" || true

# 也尝试最新图谱
if [ ! -f "${WORKSPACE}/trading/sector_map_${DATE}.md" ]; then
    import_doc "龙虾-最新-产业图谱" \
        "${WORKSPACE}/trading/产业图谱.md" || true
fi

# 5. 交易追踪
log "--- 同步交易追踪 ---"
import_doc "龙虾-最新-交易追踪" \
    "${WORKSPACE}/trading/交易追踪.md" || true

# 6. 进化日志（取最新一条）
log "--- 同步进化日志 ---"
EVO_DIR="${WORKSPACE}/trading/evolution_logs"
if [ -d "$EVO_DIR" ]; then
    LATEST_EVO=$(ls -t "$EVO_DIR"/*.md 2>/dev/null | head -1)
    if [ -n "$LATEST_EVO" ]; then
        import_doc "龙虾-${DATE_SHORT}-进化日志" "$LATEST_EVO" || true
    else
        log "⚠️  进化日志目录为空"
    fi
else
    log "⚠️  进化日志目录不存在"
fi

# 7. 今日工作日志
log "--- 同步工作日志 ---"
import_doc "龙虾-${DATE_SHORT}-工作日志" \
    "${WORKSPACE}/memory/${DATE}.md" || true

# 8. 选股历史（合并同一天所有选股文件）
log "--- 同步选股历史 ---"
SELECTION_DIR="${WORKSPACE}/trading/selection_history"
if [ -d "$SELECTION_DIR" ]; then
    TODAY_SELECTIONS=$(ls -t "$SELECTION_DIR"/*"${DATE}"*.md 2>/dev/null | head -3)
    if [ -n "$TODAY_SELECTIONS" ]; then
        for f in $TODAY_SELECTIONS; do
            local bname
            bname=$(basename "$f" .md)
            import_doc "龙虾-${bname}" "$f" || true
        done
    fi
fi

log "--- 同步完成 ---"
log "日志: $LOG_FILE"
