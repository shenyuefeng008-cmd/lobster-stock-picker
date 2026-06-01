#!/bin/bash
# IMA 同步脚本 - 将指定文件导入 IMA 知识库（含重试+校验+备份）
# 用法: bash ima_sync.sh <markdown_file_path> <title>
# 依赖: jq, curl, python3
# IMA 凭证通过 get-token.sh 动态获取
# 重试逻辑: 最多3次，每次间隔10秒
# 校验逻辑: 检查 import_doc 和 add_knowledge 是否成功
# 备份逻辑: 3次失败后保存到 ~/.qclaw/ima_backup/ 目录
# v2.1 修复: 去掉 set -e，加统一错误日志

FILE_PATH="$1"
TITLE="$2"
SKILL_DIR="/Users/yuefengshen/Library/Application Support/QClaw/openclaw/config/skills/ima"
KB_ID="SrCkw1sLQ8_BivwNA6vYZnx2bh3EjPO3kch-2upFXAw="
BACKUP_DIR="$HOME/.qclaw/ima_backup"
MAX_RETRY=3
RETRY_DELAY=10
ERROR_LOG="/tmp/ima-errors.log"

# 统一错误日志函数
log_error() {
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] IMA-SYNC [$TITLE] $1" >> "$ERROR_LOG"
}

log_info() {
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] IMA-SYNC [$TITLE] $1" >> "$ERROR_LOG"
}

# 参数检查
if [ -z "$FILE_PATH" ] || [ -z "$TITLE" ]; then
  log_error "参数缺失: FILE_PATH=$FILE_PATH TITLE=$TITLE"
  echo "用法: bash ima_sync.sh <markdown_file> <title>"
  exit 1
fi

if [ ! -f "$FILE_PATH" ]; then
  log_error "文件不存在: $FILE_PATH"
  echo "错误: 文件不存在: $FILE_PATH"
  exit 1
fi

# 创建备份目录
mkdir -p "$BACKUP_DIR"

# 获取 IMA 凭证
echo "→ 正在获取 IMA 凭证..."
CREDS=$(bash "$SKILL_DIR/get-token.sh" 2>/dev/null)
IMA_CLIENT_ID=$(echo "$CREDS" | jq -r .client_id)
IMA_API_KEY=$(echo "$CREDS" | jq -r .api_key)

if [ -z "$IMA_CLIENT_ID" ] || [ -z "$IMA_API_KEY" ]; then
  log_error "无法获取IMA凭证"
  echo "错误: 无法获取 IMA 凭证"
  # 保存到备份目录
  BACKUP_FILE="$BACKUP_DIR/$(date +%Y%m%d_%H%M%S)_$(basename "$FILE_PATH")"
  cp "$FILE_PATH" "$BACKUP_FILE"
  echo "→ 已保存到备份目录: $BACKUP_FILE"
  exit 1
fi

echo "→ 正在导入笔记: $TITLE"

# 构造 import_doc 请求体
BODY=$(python3 -c "
import json, sys
content = open('$FILE_PATH', 'r', encoding='utf-8').read()
body = {'content_format': 1, 'content': content}
print(json.dumps(body, ensure_ascii=False))
")

# 重试逻辑：import_doc
NOTE_ID=""
for i in $(seq 1 $MAX_RETRY); do
  echo "→ 尝试 import_doc (第 $i 次)..."
  
  RESP=$(curl -s -X POST "https://ima.qq.com/openapi/note/v1/import_doc" \
    -H "ima-openapi-clientid: $IMA_CLIENT_ID" \
    -H "ima-openapi-apikey: $IMA_API_KEY" \
    -H "Content-Type: application/json" \
    -d "$BODY")
  
  CODE=$(echo "$RESP" | jq -r .code)
  
  if [ "$CODE" = "0" ]; then
    NOTE_ID=$(echo "$RESP" | jq -r .data.note_id)
    echo "✅ import_doc 成功: note_id=$NOTE_ID"
    break
  else
    echo "⚠️  import_doc 失败 (第 $i 次): $RESP"
    log_error "import_doc 失败 (第 $i 次): code=$CODE"
    if [ $i -lt $MAX_RETRY ]; then
      echo "→ 等待 $RETRY_DELAY 秒后重试..."
      sleep $RETRY_DELAY
    fi
  fi
done

if [ -z "$NOTE_ID" ]; then
  log_error "import_doc 最终失败（已重试 $MAX_RETRY 次）"
  echo "错误: import_doc 失败（已重试 $MAX_RETRY 次）"
  # 保存到备份目录
  BACKUP_FILE="$BACKUP_DIR/$(date +%Y%m%d_%H%M%S)_$(basename "$FILE_PATH")"
  cp "$FILE_PATH" "$BACKUP_FILE"
  echo "→ 已保存到备份目录: $BACKUP_FILE"
  echo "→ 请稍后手动重试: bash $0 '$BACKUP_FILE' '$TITLE'"
  exit 1
fi

# 重试逻辑：add_knowledge
MEDIA_ID=""
for i in $(seq 1 $MAX_RETRY); do
  echo "→ 尝试 add_knowledge (第 $i 次)..."
  
  BODY2="{\"knowledge_base_id\":\"$KB_ID\",\"media_type\":11,\"note_info\":{\"content_id\":\"$NOTE_ID\"},\"parent_folder_id\":\"7460511260096492\"}"
  
  RESP2=$(curl -s -X POST "https://ima.qq.com/openapi/wiki/v1/add_knowledge" \
    -H "ima-openapi-clientid: $IMA_CLIENT_ID" \
    -H "ima-openapi-apikey: $IMA_API_KEY" \
    -H "Content-Type: application/json" \
    -d "$BODY2")
  
  CODE2=$(echo "$RESP2" | jq -r .code)
  
  if [ "$CODE2" = "0" ]; then
    MEDIA_ID=$(echo "$RESP2" | jq -r .data.media_id)
    echo "✅ add_knowledge 成功: media_id=$MEDIA_ID"
    break
  else
    echo "⚠️  add_knowledge 失败 (第 $i 次): $RESP2"
    log_error "add_knowledge 失败 (第 $i 次): code=$CODE2"
    if [ $i -lt $MAX_RETRY ]; then
      echo "→ 等待 $RETRY_DELAY 秒后重试..."
      sleep $RETRY_DELAY
    fi
  fi
done

if [ -z "$MEDIA_ID" ]; then
  log_error "add_knowledge 最终失败（已重试 $MAX_RETRY 次），note_id=$NOTE_ID"
  echo "警告: add_knowledge 失败（已重试 $MAX_RETRY 次），笔记已创建但未被知识库收录"
  echo "→ note_id=$NOTE_ID (请手动在 IMA 网页端添加)"
  # 不退出，笔记已创建，只是未被知识库收录
fi

echo "✅ 同步完成: note_id=$NOTE_ID, media_id=$MEDIA_ID"

# 校验：尝试搜索刚创建的笔记（可选）
echo "→ 正在校验同步结果..."
VERIFY=$(curl -s -X POST "https://ima.qq.com/openapi/wiki/v1/search_knowledge" \
  -H "ima-openapi-clientid: $IMA_CLIENT_ID" \
  -H "ima-openapi-apikey: $IMA_API_KEY" \
  -H "Content-Type: application/json" \
  -d "{\"knowledge_base_id\":\"$KB_ID\",\"keyword\":\"$TITLE\",\"page\":1,\"page_size\":5}")

VERIFY_CODE=$(echo "$VERIFY" | jq -r .code)
if [ "$VERIFY_CODE" = "0" ]; then
  VERIFY_COUNT=$(echo "$VERIFY" | jq -r '.data.total // 0')
  if [ "$VERIFY_COUNT" -gt 0 ]; then
    echo "✅ 校验成功: 知识库中已找到 '$TITLE' ($VERIFY_COUNT 条相关)"
  else
    echo "⚠️  校验警告: 知识库中未找到 '$TITLE'，但笔记已创建"
  fi
else
  echo "⚠️  校验失败: $VERIFY"
  log_error "校验失败: code=$VERIFY_CODE"
fi

log_info "同步完成: note_id=$NOTE_ID media_id=$MEDIA_ID"
exit 0
