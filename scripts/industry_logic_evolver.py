#!/usr/bin/env python3
"""
产业逻辑进化数据采集脚本 v2.0
只做数据采集，AI agent 负责推理分析和文件更新

输出JSON（/tmp/industry_evolution_YYYYMMDD.json）：
  - sector_counts:    {申万行业: 涨停数}
  - framework_text:   产业逻辑框架.md 全文（供AI解析）
  - catalyst_db:     催化剂数据库.json 全文
  - unverified:      未验证催化剂列表
  - trading_sector:   板块涨停数据（如有，供AI参考）
"""

import json, datetime, re, sys, os
from pathlib import Path

BASE = Path("/Users/yuefengshen/.qclaw/workspace-1gwpiwf3hr163jz5")
TRADING = BASE / "trading"
TODAY = datetime.date.today()
YESTERDAY = TODAY - datetime.timedelta(days=1)

def load_json(path, default=None):
    try:
        with open(path) as f:
            return json.load(f)
    except:
        return default

print("=== 产业逻辑进化数据采集 v2.0 ===\n")

# ══════════════════════════════════════════════════════
# Step 1: 获取涨停池，按申万行业统计
# ══════════════════════════════════════════════════════
print("[Step 1] 获取涨停池，按申万行业统计...")

sector_file = f"/tmp/sector_limit_up_{TODAY.strftime('%Y%m%d')}.json"
sector_data = load_json(sector_file)

if not sector_data:
    sector_file = f"/tmp/sector_limit_up_{YESTERDAY.strftime('%Y%m%d')}.json"
    sector_data = load_json(sector_file)
    if sector_data:
        print(f"  ⚠️ 今日板块数据不存在，使用昨日数据")
    else:
        # fallback: akshare
        print("  ⚠️ 板块数据文件不存在，尝试用akshare获取...")
        try:
            import akshare as ak
            date_str = YESTERDAY.strftime("%Y%m%d")
            df = ak.stock_zt_pool_em(date=date_str)
            sector_count = {}
            for _, row in df.iterrows():
                sec = str(row.get('所属行业', row.get('industry', '未知')))
                sector_count[sec] = sector_count.get(sec, 0) + 1
            sector_data = {
                'date': YESTERDAY.strftime('%Y-%m-%d'),
                'sector_counts': sector_count,
                'total_zt': len(df)
            }
            print(f"  ✅ akshare获取涨停池 {date_str}：{len(df)}只")
        except Exception as e:
            print(f"  🔴 akshare获取失败: {e}")
            sector_data = {'date': YESTERDAY.strftime('%Y-%m-%d'), 'sector_counts': {}, 'total_zt': 0}

sector_counts = sector_data.get('sector_counts', {})
print(f"  申万行业涨停统计（Top10）：")
for s, c in sorted(sector_counts.items(), key=lambda x: -x[1])[:10]:
    print(f"    {s}: {c}家涨停")
print(f"  合计：{sector_data.get('total_zt', 0)}只涨停\n")

# ══════════════════════════════════════════════════════
# Step 2: 读取产业逻辑框架.md（全文，供AI解析）
# ══════════════════════════════════════════════════════
print("[Step 2] 读取产业逻辑框架.md（供AI解析）...")

framework_path = TRADING / "产业逻辑框架.md"
framework_text = ""
if framework_path.exists():
    with open(framework_path) as f:
        framework_text = f.read()
    print(f"  ✅ 读取成功，{len(framework_text)}字符")
else:
    print(f"  🔴 文件不存在：{framework_path}")

# ══════════════════════════════════════════════════════
# Step 3: 读取催化剂数据库.json
# ══════════════════════════════════════════════════════
print("[Step 3] 读取催化剂数据库.json...")

cat_db_path = TRADING / "催化剂数据库.json"
cat_db = load_json(cat_db_path, {'catalysts': []})
catalysts = cat_db.get('catalysts', [])
unverified = [c for c in catalysts if not c.get('verified')]

print(f"  催化剂总数：{len(catalysts)}")
print(f"  未验证：{len(unverified)}")
for c in unverified[:3]:
    print(f"    - {c.get('id','?')} {c.get('sector','?')} {c.get('date','?')}")
print()

# ══════════════════════════════════════════════════════
# Step 4: 输出结果JSON
# ══════════════════════════════════════════════════════
print("[Step 4] 输出结果...")

output = {
    'date': TODAY.strftime('%Y-%m-%d'),
    'data_date': sector_data.get('date', ''),
    'sector_counts': sector_counts,          # 申万行业 → 涨停数
    'total_zt': sector_data.get('total_zt', 0),
    'framework_text': framework_text,        # AI解析
    'catalyst_db': cat_db,               # 完整数据库
    'unverified_catalysts': [
        {'id': c.get('id'), 'sector': c.get('sector'), 'date': c.get('date'), 'type': c.get('type')}
        for c in unverified
    ],
    # 提示：以下内容由AI agent分析后决策
    'ai_analysis_needed': True,
    'analysis_hints': [
        '将申万行业名与框架赛道名做语义匹配（如：元件→光模块，通用设备→工程器械）',
        '发现框架未覆盖且连续2日≥3家涨停的板块 → 新候选赛道',
        '框架赛道对应的板块今日涨停数显著上升（如2→8）→ 升级状态🔴/🟡/🟢',
        '未验证催化剂：对应板块今日有涨停→verified=true, outcome=验证通过',
    ]
}

output_path = f"/tmp/industry_evolution_{TODAY.strftime('%Y%m%d')}.json"
with open(output_path, 'w') as f:
    json.dump(output, f, ensure_ascii=False, indent=2)

print(f"  ✅ 输出：{output_path}")
print(f"  ⚠️ 注意：AI agent需读取此JSON，进行语义分析和决策")
print(f"  ⚠️ 脚本不生成建议（避免误判），全部由AI推理完成")
print()
print("=" * 50)
print("✅ 数据采集完成，交由AI agent进行进化分析")
print("=" * 50)
