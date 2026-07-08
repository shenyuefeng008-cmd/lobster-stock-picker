#!/bin/bash
# 龙虾超短交易系统 - 快速部署脚本
# 用法: bash setup_lobster.sh [target_dir]

set -e

TARGET_DIR=${1:-"/Users/$(whoami)/.qclaw/workspace-lobster"}
SOURCE_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "=========================================="
echo "龙虾超短交易系统 - 部署脚本"
echo "=========================================="
echo "源目录: $SOURCE_DIR"
echo "目标目录: $TARGET_DIR"
echo ""

# 1. 创建目标目录
if [ -d "$TARGET_DIR" ]; then
    echo "⚠️  目标目录已存在: $TARGET_DIR"
    read -p "是否覆盖？(y/N) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "❌ 部署取消"
        exit 1
    fi
    rm -rf "$TARGET_DIR"
fi

echo "📂 创建目标目录..."
mkdir -p "$TARGET_DIR"
cd "$TARGET_DIR"

# 2. 复制关键文件
echo "📋 复制关键文件..."

# 复制目录结构
cp -r "$SOURCE_DIR/scripts" .
cp -r "$SOURCE_DIR/trading" .
cp -r "$SOURCE_DIR/config" . 2>/dev/null || mkdir -p config

# 复制根文件
cp "$SOURCE_DIR/MEMORY.md" . 2>/dev/null || true
cp "$SOURCE_DIR/AGENTS.md" . 2>/dev/null || true
cp "$SOURCE_DIR/SOUL.md" . 2>/dev/null || true
cp "$SOURCE_DIR/TOOLS.md" . 2>/dev/null || true
cp "$SOURCE_DIR/RULES.md" . 2>/dev/null || true
cp "$SOURCE_DIR/IDENTITY.md" . 2>/dev/null || true
cp "$SOURCE_DIR/USER.md" . 2>/dev/null || true

# 复制交接文档
cp "$SOURCE_DIR/【交接包】龙虾超短交易系统_2026-07-01.md" . 2>/dev/null || true

# 3. 创建必要目录
echo "📁 创建目录结构..."
mkdir -p memory
mkdir -p artifacts
mkdir -p blog
mkdir -p trading/news
mkdir -p trading/reports
mkdir -p trading/five_level_snapshots

# 4. 初始化配置文件
echo "⚙️  初始化配置文件..."

if [ ! -f "config/lobster-config.json" ]; then
    cat > "config/lobster-config.json" << 'EOF'
{
  "emotion": {
    "thresholds": {"ice_point": 1600, "repair": 2000, "climax": 2500, "extreme": 3500}
  },
  "position_limits": {
    "ice_point": 30, "repair": 40, "climax": 70, "extreme": 10
  },
  "stop_loss": {
    "1.0分歧低吸": -5, "2.0板块卡位": -7, "3.0趋势低吸": -8
  },
  "take_profit": {
    "min_profit_pct": 8, "trailing_pct": 8
  },
  "scoring_models": {
    "1.0一进二": {"min_score": 60, "top_n": 5},
    "2.0板块卡位": {"min_score": 70, "top_n": 4},
    "3.0趋势低吸": {"min_score": 30, "top_n": 3}
  },
  "auto_trade": true
}
EOF
    echo "  ✅ 已创建默认配置"
fi

# 5. 初始化模拟持仓
echo "💰 初始化模拟持仓..."
if [ ! -f "trading/模拟持仓.json" ]; then
    cat > "trading/模拟持仓.json" << 'EOF'
{
  "capital": {
    "initial": 1000000,
    "available": 1000000,
    "market_value": 0,
    "total_assets": 1000000,
    "hist_pnl": 0,
    "total_pnl": 0
  },
  "positions": [],
  "trade_log": []
}
EOF
    echo "  ✅ 已创建初始持仓（100万）"
fi

# 6. 检查Python依赖
echo "🐍 检查Python依赖..."
python3 --version >/dev/null 2>&1 || {
    echo "  ❌ Python3未安装"
    exit 1
}

pip3 list 2>/dev/null | grep -q akshare || {
    echo "  ⚠️  akshare未安装，正在安装..."
    pip3 install akshare --quiet
}
pip3 list 2>/dev/null | grep -q requests || {
    echo "  ⚠️  requests未安装，正在安装..."
    pip3 install requests --quiet
}

echo "  ✅ Python依赖检查完成"

# 7. 设置文件权限
echo "🔒 设置文件权限..."
chmod +x scripts/*.sh 2>/dev/null || true
chmod +x scripts/*.py 2>/dev/null || true

# 8. 创建快速测试脚本
echo "🧪 创建测试脚本..."
cat > "test_system.sh" << 'EOF'
#!/bin/bash
# 快速测试脚本
cd "$(dirname "$0")/scripts"

echo "=== 测试1: 情绪获取 ==="
python3 get_market_sentiment.py 2>&1 | head -20

echo ""
echo "=== 测试2: 持仓状态 ==="
python3 -c "from simulated_trading import status; print(status())" 2>&1

echo ""
echo "=== 测试3: 盘中巡检（干跑）==="
python3 lobster_intraday_patrol.py 2>&1 | head -50

echo ""
echo "✅ 测试完成"
EOF
chmod +x "test_system.sh"

# 9. 部署完成
echo ""
echo "=========================================="
echo "✅ 部署完成！"
echo "=========================================="
echo "部署目录: $TARGET_DIR"
echo ""
echo "下一步："
echo "1. 阅读交接文档: cat 【交接包】龙虾超短交易系统_2026-07-01.md"
echo "2. 运行测试: cd $TARGET_DIR && bash test_system.sh"
echo "3. 配置Cron: 参考交接文档中的Cron任务时间表"
echo "4. 启动系统: openclaw cron update [cron_id] --enabled true"
echo ""
echo "⚠️  重要提醒："
echo "  - 系统会自动交易，请先阅读MEMORY.md了解风险"
echo "  - 如需暂停，执行: openclaw cron list | grep 龙虾 | awk '{print \$1}' | xargs -I {} openclaw cron update {} --enabled false"
echo ""
