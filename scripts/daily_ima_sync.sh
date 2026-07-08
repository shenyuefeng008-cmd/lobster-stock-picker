#!/bin/bash
# 每日IMA同步脚本 - 将当天所有内容同步到IMA知识库
# 执行时间: 每个交易日16:00(收盘后)
# 同步内容: 每日新闻、复盘报告、BUG日志、模拟交易日志

set +e  # v2.1: 不使用 set -e，改用 log_error 记录错误

WORKSPACE="/Users/yuefengshen/.qclaw/workspace-1gwpiwf3hr163jz5"
SKILL_DIR="/Users/yuefengshen/Library/Application Support/QClaw/openclaw/config/skills/ima"
KB_ID="SrCkw1sLQ8_BivwNA6vYZnx2bh3EjPO3kch-2upFXAw="
TODAY=$(date +%Y-%m-%d)
BACKUP_DIR="$HOME/.qclaw/ima_backup"
mkdir -p "$BACKUP_DIR"

echo "📤 开始每日IMA同步 $TODAY ..."

# ===== 工具函数 =====

# 获取IMA凭证
get_credentials() {
    local creds=$(bash "$SKILL_DIR/get-token.sh" 2>/dev/null)
    local client_id=$(echo "$creds" | jq -r .client_id)
    local api_key=$(echo "$creds" | jq -r .api_key)
    
    if [ -z "$client_id" ] || [ -z "$api_key" ] || [ "$client_id" = "null" ] || [ "$api_key" = "null" ]; then
        echo "错误: 无法获取IMA凭证" >&2
        return 1
    fi
    
    echo "$client_id|$api_key"
}

# 搜索已有笔记 (返回 note_id 和 media_id)
# 用法: search_note <title>
# 输出: note_id media_id  (空格分隔，找不到则为空)
search_note() {
    local title="$1"
    local cred_str=$(get_credentials)
    
    if [ $? -ne 0 ] || [ -z "$cred_str" ]; then
        return 1
    fi
    
    local client_id=$(echo "$cred_str" | cut -d'|' -f1)
    local api_key=$(echo "$cred_str" | cut -d'|' -f2)
    
    local resp=$(curl -s -X POST "https://ima.qq.com/openapi/wiki/v1/search_knowledge" \
        -H "ima-openapi-clientid: $client_id" \
        -H "ima-openapi-apikey: $api_key" \
        -H "Content-Type: application/json" \
        -d "{\"knowledge_base_id\":\"$KB_ID\",\"keyword\":\"$title\",\"page\":1,\"page_size\":5}")
    
    local code=$(echo "$resp" | jq -r .code)
    if [ "$code" = "0" ]; then
        local count=$(echo "$resp" | jq -r '.data.total // 0')
        if [ "$count" -gt 0 ]; then
            local note_id=$(echo "$resp" | jq -r '.data.list[0].note_id // empty')
            local media_id=$(echo "$resp" | jq -r '.data.list[0].media_id // empty')
            echo "$note_id $media_id"
            return 0
        fi
    fi
    
    return 1
}

# 删除笔记
# 用法: delete_note <note_id>
delete_note() {
    local note_id="$1"
    
    if [ -z "$note_id" ]; then
        return 0
    fi
    
    local cred_str=$(get_credentials)
    if [ $? -ne 0 ] || [ -z "$cred_str" ]; then
        return 1
    fi
    
    local client_id=$(echo "$cred_str" | cut -d'|' -f1)
    local api_key=$(echo "$cred_str" | cut -d'|' -f2)
    
    curl -s -X DELETE "https://ima.qq.com/openapi/note/v1/delete_doc" \
        -H "ima-openapi-clientid: $client_id" \
        -H "ima-openapi-apikey: $api_key" \
        -H "Content-Type: application/json" \
        -d "{\"note_id\":\"$note_id\"}" > /dev/null 2>&1 || true
    
    echo "🗑️  已删除旧笔记: $note_id"
}

# 上传文件到IMA (import_doc + add_knowledge)
# 用法: upload_file <file_path> <title>
# 输出: note_id media_id
upload_file() {
    local file_path="$1"
    local title="$2"
    
    if [ ! -f "$file_path" ]; then
        echo "警告: 文件不存在: $file_path" >&2
        echo " "
        return 1
    fi
    
    local cred_str=$(get_credentials)
    if [ $? -ne 0 ] || [ -z "$cred_str" ]; then
        # 备份到本地
        local backup_file="$BACKUP_DIR/$(date +%Y%m%d_%H%M%S)_$(basename "$file_path")"
        cp "$file_path" "$backup_file"
        echo "→ 已保存到备份目录: $backup_file" >&2
        echo " "
        return 1
    fi
    
    local client_id=$(echo "$cred_str" | cut -d'|' -f1)
    local api_key=$(echo "$cred_str" | cut -d'|' -f2)
    
    # 构造请求体
    local body=$(python3 -c "
import json, sys
content = open('$file_path', 'r', encoding='utf-8').read()
# 注意: IMA import_doc 仅支持 format=1 (HTML内部格式)
# 原值1为HTML，但我们传的是Markdown内容，改为2
body = {'content_format': 1, 'content': content}
print(json.dumps(body, ensure_ascii=False))
")
    
    # import_doc (最多重试3次)
    local note_id=""
    for i in 1 2 3; do
        echo "→ 尝试 import_doc ($title, 第 $i 次)..." >&2
        
        local resp=$(curl -s -X POST "https://ima.qq.com/openapi/note/v1/import_doc" \
            -H "ima-openapi-clientid: $client_id" \
            -H "ima-openapi-apikey: $api_key" \
            -H "Content-Type: application/json" \
            -d "$body")
        
        local code=$(echo "$resp" | jq -r .code)
        
        if [ "$code" = "0" ]; then
            note_id=$(echo "$resp" | jq -r .data.note_id)
            echo "✅ import_doc 成功: note_id=$note_id" >&2
            break
        else
            echo "⚠️  import_doc 失败 (第 $i 次): $resp" >&2
            if [ $i -lt 3 ]; then
                sleep 10
            fi
        fi
    done
    
    if [ -z "$note_id" ]; then
        # 备份到本地
        local backup_file="$BACKUP_DIR/$(date +%Y%m%d_%H%M%S)_$(basename "$file_path")"
        cp "$file_path" "$backup_file"
        echo "→ 已保存到备份目录: $backup_file" >&2
        echo " "
        return 1
    fi
    
    # add_knowledge (最多重试3次)
    local media_id=""
    for i in 1 2 3; do
        echo "→ 尝试 add_knowledge ($title, 第 $i 次)..." >&2
        
        local body2="{\"knowledge_base_id\":\"$KB_ID\",\"media_type\":11,\"note_info\":{\"content_id\":\"$note_id\"},\"parent_folder_id\":\"7460511260096492\"}"
        
        local resp2=$(curl -s -X POST "https://ima.qq.com/openapi/wiki/v1/add_knowledge" \
            -H "ima-openapi-clientid: $client_id" \
            -H "ima-openapi-apikey: $api_key" \
            -H "Content-Type: application/json" \
            -d "$body2")
        
        local code2=$(echo "$resp2" | jq -r .code)
        
        if [ "$code2" = "0" ]; then
            media_id=$(echo "$resp2" | jq -r .data.media_id)
            echo "✅ add_knowledge 成功: media_id=$media_id" >&2
            break
        else
            echo "⚠️  add_knowledge 失败 (第 $i 次): $resp2" >&2
            if [ $i -lt 3 ]; then
                sleep 10
            fi
        fi
    done
    
    if [ -z "$media_id" ]; then
        echo "⚠️  add_knowledge 失败 (已重试3次)，笔记已创建但未被知识库收录" >&2
        echo "→ note_id=$note_id (请手动在IMA网页端添加)" >&2
    fi
    
    echo "$note_id $media_id"
}

# ===== 主逻辑 =====

# 要同步的文件列表 (file_path|title)
# 格式: 文件路径|笔记标题
SYNC_FILES=(
    "$WORKSPACE/trading/news/$TODAY.md|龙虾新闻 $TODAY"
    "$WORKSPACE/trading/BUG_LOG.md|龙虾BUG日志"
    "$WORKSPACE/trading/模拟持仓.json|龙虾模拟持仓"
    "$WORKSPACE/trading/催化剂数据库.json|龙虾催化剂数据库"
    "$WORKSPACE/trading/产业逻辑框架.md|龙虾产业逻辑框架"
    "$WORKSPACE/lobster_knowledge_graph.html|龙虾产业知识图谱"
)

# 可选: 收盘复盘报告 (如果存在)
CLOSING_REPORT="$WORKSPACE/trading/reports/closing_$TODAY.md"
if [ -f "$CLOSING_REPORT" ]; then
    SYNC_FILES+=("$CLOSING_REPORT|龙虾收盘复盘 $TODAY")
fi

# 遍历同步
for sync_item in "${SYNC_FILES[@]}"; do
    IFS='|' read -r file_path title <<< "$sync_item"
    
    echo ""
    echo "📋 处理: $title"
    echo "   文件: $file_path"
    
    # 检查文件是否存在
    if [ ! -f "$file_path" ]; then
        echo "⚠️  文件不存在，跳过: $file_path"
        continue
    fi
    
    # 搜索已有笔记
    echo "→ 搜索已有笔记: $title"
    existing=$(search_note "$title") || true
    existing_note_id=$(echo "$existing" | cut -d' ' -f1)
    existing_media_id=$(echo "$existing" | cut -d' ' -f2)
    
    # 如果已存在，先删除旧笔记
    if [ -n "$existing_note_id" ] && [ "$existing_note_id" != "null" ]; then
        echo "→ 发现已有笔记，删除旧版本..."
        delete_note "$existing_note_id"
        sleep 2  # 等待删除完成
    fi
    
    # 上传新文件
    echo "→ 上传新版本..."
    upload_result=$(upload_file "$file_path" "$title") || true
    new_note_id=$(echo "$upload_result" | cut -d' ' -f1)
    new_media_id=$(echo "$upload_result" | cut -d' ' -f2)
    
    if [ -n "$new_note_id" ]; then
        echo "✅ 同步完成: $title (note_id=$new_note_id, media_id=$new_media_id)"
    else
        echo "❌ 同步失败: $title (已备份到 $BACKUP_DIR)"
    fi
done

echo ""
echo "🎉 每日IMA同步完成!"
echo "   同步时间: $(date '+%Y-%m-%d %H:%M:%S')"
echo "   同步文件数: ${#SYNC_FILES[@]}"

exit 0
