# 龙虾收盘复盘 — cron 任务指令（v4）

> **执行时间**：交易日 15:05
> **前置任务**：读取本日盘前选股+竞价选股+午间复盘笔记
> **输出**：完整复盘报告（按复盘模板格式）+ 更新选股历史

**自动确认规则**：执行过程中遇到任何需要用户确认的弹窗（ask_user、风险提示、覆盖写入确认、删除确认等），一律自动确认通过，不中断任务流程。
## 📎 任务反馈链 — 读取上游建议

**执行任务前，必须先读取 `trading/task-feedback-chain.md` 文件**，查找当日最新的上游任务结论和"给下个任务"建议。
将上游建议融入你的执行决策，但不要盲目照搬——结合当前实际情况判断。

- 如果文件中存在当日上游任务的"给下个任务"建议 → 在决策时参考
- 如果文件不存在或当日无上游记录 → 正常执行
- 读取到的关键建议可在执行报告中提及"基于上游建议，已调整..."
---

## 步骤0：前置任务校验（必做）

```bash
python3 << 'PYEOF'
import json, datetime, sys

today = datetime.date.today().strftime('%Y-%m-%d')
errors = []

# 检查盘前候选池JSON
try:
    with open('/tmp/lobster_premarket_candidates.json') as f:
        data = json.load(f)
    if data.get('date') != today:
        errors.append(f"盘前候选池JSON日期={data.get('date')}，非今天{today}")
    else:
        print(f"✅ 盘前候选池JSON正常 (日期={today}, 情绪={data['emotion'].get('主导维度','?')})")
except FileNotFoundError:
    errors.append("盘前候选池JSON不存在 — 07:00盘前选股任务可能失败")
except Exception as e:
    errors.append(f"盘前候选池JSON读取失败: {e}")

# 检查竞价选股结果JSON
try:
    with open('/tmp/lobster_bid_result.json') as f:
        data = json.load(f)
    if data.get('date') != today:
        errors.append(f"竞价选股JSON日期={data.get('date')}，非今天{today}")
    else:
        results = data.get('results', {})
        found = sum(1 for v in results.values() if v)
        print(f"✅ 竞价选股JSON正常 (日期={today}, 选出{found}只)")
except FileNotFoundError:
    errors.append("竞价选股JSON不存在 — 09:25竞价选股任务可能失败")
except Exception as e:
    errors.append(f"竞价选股JSON读取失败: {e}")

# 检查午间复盘文件
try:
    with open(f'/tmp/lobster_midday_{today}.md') as f:
        content = f.read()
    print(f"✅ 午间复盘文件存在 ({len(content)}字节)")
except FileNotFoundError:
    errors.append("午间复盘文件不存在 — 11:30午间复盘任务可能失败")

# 检查关注股.md
try:
    with open('/Users/yuefengshen/.qclaw/workspace-1gwpiwf3hr163jz5/trading/关注股.md') as f:
        content = f.read()
    if len(content) < 50:
        errors.append("关注股.md内容过短，可能异常")
    else:
        print(f"✅ 关注股.md正常 ({len(content)}字节)")
except FileNotFoundError:
    errors.append("关注股.md不存在")

if errors:
    print(f"\n{'='*60}")
    print(f"🚨 前置校验失败 ({len(errors)}个问题):")
    for e in errors:
        print(f"  ❌ {e}")
    print(f"{'='*60}")
    print(f"⚠️ 警告：以下数据缺失，复盘结论可能不准确！")
    print(f"⚠️ 建议：检查前置任务是否正常运行")
    print(f"{'='*60}\n")
else:
    print("\n✅ 所有前置校验通过")
PYEOF
```

## 步骤0.7：新赛道检测硬约束（必做）

> **目标**：自动识别连续2日爆发的板块，提示人工审核是否加入产业逻辑框架

```bash
python3 << 'PYEOF'
import json, akshare as ak, sys, os
from datetime import datetime, timedelta
from pathlib import Path

# 添加scripts目录到Python路径
scripts_dir = Path('/Users/yuefengshen/.qclaw/workspace-1gwpiwf3hr163jz5/scripts')
sys.path.insert(0, str(scripts_dir))

today = datetime.now().strftime('%Y%m%d')
yday = (datetime.now() - timedelta(days=1)).strftime('%Y%m%d')
today_f = Path(f'/tmp/sector_limit_up_{today}.json')
yday_f = Path(f'/tmp/sector_limit_up_{yday}.json')

# 保存今日板块涨停数据
try:
    df = ak.stock_zt_pool_em(date=today)
    # 统计板块涨停家数（所属行业）
    board_cnt = {}
    for _, row in df.iterrows():
        board = row.get('所属行业', '未知')
        board_cnt[board] = board_cnt.get(board, 0) + 1
    with open(today_f, 'w') as f:
        json.dump({'date': today, 'board': board_cnt}, f, ensure_ascii=False)
    print(f"✅ 今日板块涨停数据已保存 ({len(board_cnt)}个板块)")
except Exception as e:
    print(f"⚠️ 保存今日数据失败: {e}")
    exit(0)

# 检测连续2日≥3家涨停
if yday_f.exists():
    with open(yday_f) as f:
        d1 = json.load(f)
    with open(today_f) as f:
        d2 = json.load(f)
    
    # 找出连续2日≥3家涨停的板块
    new = [b for b in d2['board'] if d2['board'][b] >= 3 and b in d1['board'] and d1['board'][b] >= 3]
    
    if new:
        print(f"🚨 新赛道候选（连续2日≥3家涨停）: {new}")
        
        # 板块名称标准化
        try:
            from normalize_sector_name import normalize_sector_name
            
            normalized_new = [normalize_sector_name(b) for b in new]
            print(f"   标准化后: {normalized_new}")
        except Exception as e:
            print(f"⚠️ 板块名称标准化失败: {e}, 使用原始名称")
            normalized_new = new
        
        # 检查是否在产业逻辑框架中（使用标准化名称）
        framework = Path('/Users/yuefengshen/.qclaw/workspace-1gwpiwf3hr163jz5/trading/产业逻辑框架.md').read_text()
        pending = []
        for orig, norm in zip(new, normalized_new):
            if norm not in framework:
                pending.append(f"{orig}（→{norm}）")
        
        if pending:
            with open('/tmp/pending_tracks.md', 'a') as f:
                for b in pending:
                    f.write(f"- [ ] {b}（{today} 连续2日≥3家涨停）\n")
            print(f"   已写入 /tmp/pending_tracks.md，下次进化任务时审核")
        else:
            print("✅ 所有候选赛道已在框架中")
    else:
        print("✅ 无新赛道候选")
else:
    print(f"⚠️ 昨日数据缺失，跳过检测")
PYEOF
```

## 步骤1.6：催化日历滚动更新（必做）

> 每次收盘复盘必须更新 `trading/催化日历.md`——已兑现移归档、已落空填原因、新催化加入近期区。

```bash
# 读取今日催化日历
cat /Users/yuefengshen/.qclaw/workspace-1gwpiwf3hr163jz5/trading/催化日历.md

# 对照今日市场数据，判断是否有催化兑现/落空
# 兑现：标注✅ + 兑现日期，移入「已兑现催化归档区」
# 落空：标注❌ + 落空原因 + 对赛道影响，移入「落空催化归档区」
# 新催化：追加至「近期催化」

# 用 edit 工具修改文件（不要全文件覆盖，仅更新变化的部分）
# 更新后确认文件顶部「最后更新」日期已改为今日

# 示例兑现判断逻辑（需人工确认，不强制）：
# - 某催化事件在今日有明确的市场验证信号 → 兑现
# - 某催化预期日期已过但无任何市场反应 → 落空
# - 某赛道持续横盘且无资金关注超过10个交易日 → 评估是否将相关催化标记落空
```

> ⚡ 提示：只需关注「近期催化」区的未决事件，已在归档区的不重复处理。

---

## 步骤1.7：收盘要闻存档（必做）

> 收盘复盘时，将今日收盘后的重要新闻/政策写入新闻存档。

**操作**：
1. **读取已有新闻（去重）**：先读 `trading/news/YYYY-MM-DD.md` 提取已有标题列表
   ```bash
   python3 /Users/yuefengshen/.qclaw/workspace-1gwpiwf3hr163jz5/scripts/news_dedupe.py /Users/yuefengshen/.qclaw/workspace-1gwpiwf3hr163jz5/trading/news/$(date +%Y-%m-%d).md
   ```
2. 使用 `tencent-news` 搜索今日收盘后重要新闻（关键词：`A股 收盘 政策 公告`）
3. **去重**：将搜索结果与步骤1的已有标题对比，剔除重复条目
4. 将**去重后的新增条目**写入 `trading/news/YYYY-MM-DD.md` 的【收盘要闻】区
5. 格式：`| MM-DD | 标题 | 来源名+URL | 赛道/板块 | 🔴高/🟡中/🟢低 | ✅已核实/⚠️待核实/❌存疑 |`
6. **发布日期**：标注新闻原始发布日期（非采集日期），未知标`未知`并降级为⚠️待核实
7. **核实状态**：官方来源(A级)直接✅，主流媒体(B级)需1次交叉验证，自媒体(C级)需2次，营销号(D级)默认❌存疑
8. 如果文件已存在（盘前已创建），只追加到【收盘要闻】区
9. 如果文件不存在，先创建完整模板再填写
10. 特别关注：与催化日历未决事件相关的新闻 → 同时写入【催化剂相关新闻】区

---

## 步骤0.5：读取复盘模板（必做）

```bash
# 读取复盘模板，按9个章节输出
cat ~/.qclaw/workspace-1gwpiwf3hr163jz5/trading/复盘模板.md
```

---

## 步骤1：获取市场数据（实时）

```bash
python3 << 'PYEOF'
import subprocess, re, datetime, json

# 指数涨跌（腾讯接口，实时）
r1 = subprocess.run(["curl","-s","https://qt.gtimg.cn/q=sh000001,sz399001,sz399006"], capture_output=True, timeout=15)
raw1 = r1.stdout
for enc in ["gb2312","gbk","utf-8"]:
    try: txt1 = raw1.decode(enc); break
    except: continue
else: txt1 = raw1.decode("utf-8","replace")
indices = {}
for line in txt1.split(";"):
    m = re.search(r'v_(\w+)="([^"]*)"', line)
    if m:
        parts = m.group(2).split("~")
        if len(parts) > 32:
            name = parts[1]
            price = parts[4]  # parts[4]=当前价
            pct = parts[32]
            indices[name] = f"{price}({pct}%)"
            print(f"{name}: {price} ({pct}%)")

# 涨跌家数（legulegu，实时）
r2 = subprocess.run(["curl","-s","-L","--max-time","15","-A","Mozilla/5.0","https://legulegu.com/stockdata/market-activity"], capture_output=True, text=True, timeout=20)
m2 = re.search(r'content="(2026-[^"]+)"', r2.stdout)
emotion_text = m2.group(1) if m2 else "获取失败"
print(f"\n涨跌家数: {emotion_text}")

# 解析涨跌家数数字
m_up = re.search(r'(\d+)家上涨', emotion_text)
m_down = re.search(r'(\d+)家下跌', emotion_text)
up_count = int(m_up.group(1)) if m_up else 0
down_count = int(m_down.group(1)) if m_down else 0

# 情绪判定
if up_count < 1000:
    emotion = "冰点"
elif up_count < 1500:
    emotion = "偏弱"
elif up_count < 2500:
    emotion = "正常"
elif up_count < 3500:
    emotion = "高潮"
else:
    emotion = "极度高潮"

# 维度判定
if up_count < 1500:
    dimension = "1.0"
    pos_limit = 3
elif up_count < 2500:
    dimension = "1.0+3.0"
    pos_limit = 5
elif up_count < 3500:
    dimension = "2.0+1.0"
    pos_limit = 7
else:
    dimension = "辅助"
    pos_limit = 2

print(f"情绪判定: {emotion}")
print(f"主导维度: {dimension}")
print(f"总仓位上限: {pos_limit}%")

# 保存到文件供后续使用
result = {
    "indices": indices,
    "up_count": up_count,
    "down_count": down_count,
    "emotion": emotion,
    "dimension": dimension,
    "pos_limit": pos_limit,
    "emotion_text": emotion_text
}
with open("/tmp/lobster_closing_data.json", "w") as f:
    json.dump(result, f, ensure_ascii=False, indent=2)

# L1情绪反馈记录（追加到 feedback.json）
import os as _os, datetime as _dt
L1_FEEDBACK_PATH = f"{WS_PATH}/trading/feedback.json"
try:
    fb = json.load(open(L1_FEEDBACK_PATH)) if _os.path.exists(L1_FEEDBACK_PATH) else {}
    if 'L1_emotion' not in fb:
        fb['L1_emotion'] = {'records': [], 'stats': {'total_predictions': 0, 'last_updated': ''}, 'parameter_adjustments': []}
    early_up = early_emo = None
    if _os.path.exists('/tmp/lobster_early_emotion.json'):
        try:
            ee = json.load(open('/tmp/lobster_early_emotion.json'))
            early_up = ee.get('up_count')
            early_emo = ee.get('emo_tag')
        except: pass
    today_rec = {
        'date': today,
        'time': _dt.datetime.now().strftime('%H:%M'),
        'actual_up': up_count,
        'actual_down': down_count,
        'actual_emo': emotion,
        'actual_dim': dimension,
        'early_up': early_up,
        'early_emo': early_emo,
        'pos_limit': pos_limit
    }
    fb['L1_emotion']['records'].append(today_rec)
    fb['L1_emotion']['stats']['total_predictions'] = len(fb['L1_emotion']['records'])
    fb['L1_emotion']['stats']['last_updated'] = today
    json.dump(fb, open(L1_FEEDBACK_PATH, 'w'), ensure_ascii=False, indent=2)
    print(f"L1情绪记录已追加: {emotion}({up_count}) 早盘={early_emo or '无'}")
except Exception as e:
    print(f"L1情绪记录失败: {e}")
PYEOF
```

---

## 步骤1.5：趋势容量池自动更新（由独立cron处理）

> ⚠️ 趋势池更新已由独立cron任务 `龙虾趋势池收盘更新` 于15:06自动执行（直接shell命令，无需agent介入）。
> 此处不再重复执行，避免重复触发腾讯API。进入下一节。

---

## 步骤2：获取涨停池数据（含二次验证）

```bash
python3 << 'PYEOF'
import akshare as ak, datetime, re, subprocess, json

# 今日涨停池
zt_today = ak.stock_zt_pool_em()
print("=== 今日涨停池 ===")
print(zt_today[['代码', '名称', '涨停统计', '所属行业', '涨停原因类别']].head(30).to_string())

# 统计板块涨停数
if '所属行业' in zt_today.columns:
    sector_counts = zt_today['所属行业'].value_counts().head(10)
    print("\n=== 板块涨停排名 ===")
    print(sector_counts.to_string())

# 昨日涨停今日表现（判断昨日日期）
today = datetime.date.today()
weekday = today.weekday()
if weekday == 0:  # 周一
    yesterday = today - datetime.timedelta(days=3)
else:
    yesterday = today - datetime.timedelta(days=1)

try:
    zt_prev = ak.stock_zt_pool_previous_em(date=yesterday.strftime('%Y%m%d'))
    print(f"\n=== 昨日涨停今日表现（{yesterday}）===")
    print(zt_prev[['代码', '名称', '涨跌幅', '连板数']].head(20).to_string())
except Exception as e:
    print(f"获取昨日涨停失败: {e}")

# ⚠️ 新增：涨停二次验证（必须执行）
print("\n=== 涨停二次验证 ===")

def get_zhangting_limit(代码):
    """根据代码判断涨跌幅限制"""
    if 代码.startswith('688'):  # 科创板
        return 0.2
    elif 代码.startswith('300'):  # 创业板
        return 0.2
    elif 代码.startswith('8') or 代码.startswith('4'):  # 北交所
        return 0.3
    else:
        return 0.1  # 主板

# 批量获取涨停股实时数据
zt_codes = zt_today['代码'].head(30).tolist()
if zt_codes:
    # 构造查询字符串
    query_codes = []
    for code in zt_codes:
        if code.startswith('6'):
            query_codes.append(f"sh{code}")
        else:
            query_codes.append(f"sz{code}")
    
    query = ','.join(query_codes)
    r = subprocess.run(["curl", "-s", f"https://qt.gtimg.cn/q={query}"], 
                      capture_output=True, timeout=15)
    raw = r.stdout
    for enc in ["gb2312","gbk","utf-8"]:
        try: txt = raw.decode(enc); break
        except: continue
    else: txt = raw.decode("utf-8","replace")
    
    # 解析数据
    verify_results = []
    for line in txt.split(";"):
        m = re.search(r'v_(\w+)="([^"]*)"', line)
        if m:
            parts = m.group(2).split("~")
            if len(parts) > 32:
                代码 = parts[2]
                名称 = parts[1]
                现价 = float(parts[4])  # parts[4]=当前价
                昨收 = float(parts[3])  # parts[3]=昨收
                涨跌幅 = float(parts[32])
                
                # 计算涨停价
                limit = get_zhangting_limit(代码)
                涨停价 = 昨收 * (1 + limit)
                
                # 判断是否真的涨停
                实际涨停 = 现价 >= 涨停价 * 0.995
                
                if 实际涨停:
                    涨停类型 = "20cm涨停" if limit >= 0.19 else "涨停"
                else:
                    涨停类型 = f"未涨停（涨幅{涨跌幅:.2f}%）"
                
                verify_results.append((名称, 代码, 涨跌幅, 涨停类型, 实际涨停))
    
    # 输出验证结果
    for 名称, 代码, 涨跌幅, 涨停类型, 实际涨停 in verify_results:
        status = "✅" if 实际涨停 else "⚠️"
        print(f"{status} {名称}({代码}): {涨跌幅:.2f}% → {涨停类型}")

print("\n验证完成")
PYEOF
```

---

## 步骤3：读取关注股（今日候选）

```bash
# 读取今日最终关注股
cat ~/.qclaw/workspace-1gwpiwf3hr163jz5/trading/关注股.md

# 或从盘前候选池JSON读取
python3 -c "import json; print(json.dumps(json.load(open('/tmp/lobster_premarket_candidates.json')), ensure_ascii=False, indent=2))"
```

---

## 步骤3.5：读取模拟仓数据（必须执行，供步骤4第10章使用）

> **必须执行**：读取今日模拟交易数据，步骤4输出第10章时不得写"待读取"或"0只"

```bash
python3 << 'PYEOF'
import json, datetime

today = datetime.date.today().strftime('%Y-%m-%d')
pos_file = '/Users/yuefengshen/.qclaw/workspace-1gwpiwf3hr163jz5/trading/模拟持仓.json'

try:
    with open(pos_file) as f:
        data = json.load(f)
except Exception as e:
    print(f'⚠️ 读取模拟持仓失败: {e}')
    exit(0)

# 今日买卖记录
today_buys = [t for t in data.get('trade_log', []) if t['type'] == 'BUY' and t['date'] == today]
today_sells = [t for t in data.get('trade_log', []) if t['type'] == 'SELL' and t['date'] == today]
positions = data.get('positions', [])

print(f'📊 模拟仓数据 ({today})')
print(f'   总资产: {data["capital"]["total_assets"]:,.0f}  可用: {data["capital"]["available"]:,.0f}  市值: {data["capital"]["market_value"]:,.2f}')
print()

if today_buys:
    print(f'📥 今日买入 {len(today_buys)} 笔:')
    for t in today_buys:
        print(f'   ✅ {t["name"]}({t["code"]})  {t["shares"]}股@{t["price"]:.2f}  维度:{t["dimension"]}  理由:{t.get("reason","")}')
else:
    print('📥 今日无买入')

if today_sells:
    print(f'\n📤 今日卖出 {len(today_sells)} 笔:')
    for t in today_sells:
        print(f'   🔴 {t["name"]}({t["code"]})  {t["shares"]}股@{t["price"]:.2f}  盈亏{t["pnl_pct"]:+.2f}%  原因:{t.get("reason",t.get("sell_type",""))}')
else:
    print('\n📤 今日无卖出')

if positions:
    print(f'\n📌 当前持仓 {len(positions)} 只:')
    for p in positions:
        cost_price = p.get('cost', 0) / p['shares'] if p['shares'] else 0
        print(f'   🏗 {p["name"]}({p["code"]})  {p["shares"]}股  成本{cost_price:.2f}  浮盈{p.get("floating_pnl",0):+.0f}元')
else:
    print('\n📌 当前空仓')

print()
print('='*50)
print('✅ 以上数据必须在复盘报告第10章「模拟仓表现」中填写，不得写"待读取"或"0只"')
PYEOF
```

---

## 步骤3.6：查询断板股（必须执行，供步骤4第2章使用）

> **必须执行**：对比昨日涨停池与今日涨停池，找出「昨日涨停→今日未涨停」的断板股。步骤4输出第2章时不得写"待补充"。

```bash
python3 << 'PYEOF'
import datetime, json, subprocess, sys
try:
    import akshare as ak
except:
    print('⚠️ akshare未安装')
    sys.exit(0)

today_dt = datetime.date.today()
yesterday_dt = today_dt - datetime.timedelta(days=1)
today_str = today_dt.strftime('%Y-%m-%d')
yesterday_str = yesterday_dt.strftime('%Y-%m-%d')

def get_zt_pool(date_str):
    try:
        df = ak.stock_zt_pool_em(date=date_str)
        if df is not None and len(df) > 0:
            return df
    except:
        pass
    return None

df_yest = get_zt_pool(yesterday_str)
df_today = get_zt_pool(today_str)

print(f'📋 断板股分析（{yesterday_str}→{today_str}）')

if df_yest is None or len(df_yest) == 0:
    print(f'  ⚠️ 昨日({yesterday_str})涨停池数据获取失败，无法计算断板股')
    print('  建议：用legulegu.com涨停数据或手动补充')
else:
    yest_codes = set(df_yest['代码'].astype(str).tolist())
    yest_names = dict(zip(df_yest['代码'].astype(str), df_yest['名称'].astype(str)))
    yest_lb = dict(zip(df_yest['代码'].astype(str), df_yest['连板数'].astype(str))) if '连板数' in df_yest.columns else {}
    
    if df_today is not None and len(df_today) > 0:
        today_codes = set(df_today['代码'].astype(str).tolist())
    else:
        today_codes = set()
    
    broken = sorted(yest_codes - today_codes)
    continued = sorted(yest_codes & today_codes)
    
    print(f'  昨日涨停：{len(yest_codes)}只 | 今日继续涨停：{len(continued)}只 | 断板：{len(broken)}只')
    
    if broken:
        print(f'\n  🔴 断板股（昨日涨停→今日未涨停）：')
        for code in broken[:15]:
            name = yest_names.get(code, code)
            lb = yest_lb.get(code, '?')
            print(f'    - {name}({code})  昨日{lb}板')
    else:
        print('  ✅ 无断板股（昨日涨停股今日全部继续涨停）')
    
    if continued:
        print(f'\n  ✅ 继续涨停股：')
        for code in continued[:10]:
            name = yest_names.get(code, code)
            lb = yest_lb.get(code, '?')
            print(f'    - {name}({code})  昨日{lb}板→今日继续')

print()
print('='*50)
print('✅ 以上断板股数据必须在复盘报告第2章「连板梯队分析-断板股」中填写，不得写"待补充"')
PYEOF
```

---

## 步骤4：按复盘模板输出（10个章节）

> **必须严格按 `复盘模板.md` 格式输出，不得遗漏章节**

### 章节内容：

1. **情绪周期判定**：指数涨跌 + 涨跌家数 + 情绪定位
2. **连板梯队分析**：按连板数表格 + 断板分析
3. **板块轮动分析**：最强板块表格 + 产业逻辑对照
4. **昨日选股今日表现**：从关注股读取 + 逐只分析
5. **明日候选标的**：4档候选池（每档3-5只）
6. **模式审计**：按 lobster-rules.md 审计6项
7. **明日策略**：若情绪X则维度Y + 仓位Z
8. **每日进化（待办）**：记录错误 + 优化建议
10. **模拟仓表现**：持仓盈亏 + 买卖操作 + 卖点信号 🌟新

---

## 步骤5：自动更新选股历史（必须执行）

```bash
python3 << 'PYEOF'
import datetime, json, re

today = datetime.date.today().strftime('%Y-%m-%d')

# 读取今日竞价选股结果（从JSON）
try:
    with open('/tmp/lobster_bid_result.json') as f:
        bid_result = json.load(f)
except:
    bid_result = {'results': {}}

# 如果JSON不存在，从关注股.md读取
if not bid_result.get('results'):
    try:
        with open("/Users/yuefengshen/.qclaw/workspace-1gwpiwf3hr163jz5/trading/关注股.md") as f:
            watch_list = f.read()
        # 提取关注股（每档第1只）
        lines = watch_list.split('\n')
        results = {}
        for line in lines:
            if '##' in line and '一进二' in line:
                tier = '1.0一进二'
            elif '##' in line and '分歧低吸' in line:
                tier = '1.0分歧低吸'
            elif '##' in line and '板块卡位' in line:
                tier = '2.0板块卡位'
            elif '##' in line and '趋势低吸' in line:
                tier = '3.0趋势低吸'
            elif line.startswith('- ') and tier:
                # 提取股票名称和代码
                m = re.search(r'([^\(]+)\((\d{6})\)', line)
                if m:
                    results[tier] = {'name': m.group(1).strip(), 'code': m.group(2)}
        bid_result = {'results': results, 'date': today}
    except:
        pass

# 读取选股历史文件
history_file = "/Users/yuefengshen/.qclaw/workspace-1gwpiwf3hr163jz5/trading/选股历史.md"
try:
    with open(history_file) as f:
        history = f.read()
except:
    history = ""

# 检查今日是否已记录
if today in history and '竞价选股' in history:
    print(f"✅ 今日（{today}）选股历史已存在，跳过写入")
else:
    # 构造历史记录条目
    entries = []
    for tier, stock in bid_result.get('results', {}).items():
        if stock and isinstance(stock, dict):
            name = stock.get('name', '未知')
            code = stock.get('code', '000000')
            change_pct = stock.get('change_pct', 0)
            
            # 构造买入条件（简化版）
            if '一进二' in tier:
                buy_cond = f"若秒板则排板"
            elif '分歧低吸' in tier:
                buy_cond = f"若低开后企稳则低吸"
            elif '板块卡位' in tier:
                buy_cond = f"若回踩5日线不破则低吸"
            elif '趋势低吸' in tier:
                buy_cond = f"若回踩5日线不破则低吸"
            else:
                buy_cond = "待确定"
            
            entries.append(f"| {today} | 竞价选股 | {name}({code}) | {buy_cond} | 待验证 | 待验证 | - | - |")
    
    # 找到表格位置并追加
    if entries:
        # 找到表格最后一行
        lines = history.split('\n')
        insert_pos = -1
        for i, line in enumerate(lines):
            if line.startswith('|') and '待验证' in line:
                insert_pos = i
            elif line.startswith('|') and '日期' in line:
                # 找到表头后的分隔行
                if i+1 < len(lines) and lines[i+1].startswith('|') and '---' in lines[i+1]:
                    insert_pos = i + 1
        
        # 如果找不到合适位置，追加到表格最后
        if insert_pos == -1:
            # 在"## 准确率统计"之前插入
            for i, line in enumerate(lines):
                if '准确率统计' in line:
                    insert_pos = i
                    break
            
            if insert_pos > 0:
                lines.insert(insert_pos, '\n'.join(entries) + '\n')
            else:
                # 追加到文件末尾
                history += '\n'.join(entries) + '\n'
        else:
            # 在找到的位置后追加
            lines.insert(insert_pos + 1, '\n'.join(entries) + '\n')
            history = '\n'.join(lines)
        
        # 写入文件
        with open(history_file, 'w') as f:
            f.write(history)
        
        print(f"✅ 已追加写入选股历史.md（{len(entries)}条记录）")
        for entry in entries:
            print(f"  - {entry}")
    else:
        print("⚠️ 未找到今日选股结果")
PYEOF
```

---

## 步骤6.5：更新系统状态（新增）

> 收盘后更新系统状态.json的yesterday数据

```bash
python3 /Users/yuefengshen/.qclaw/workspace-1gwpiwf3hr163jz5/scripts/update_system_status.py
```

---

## 步骤7：发送消息给用户

```bash
# 发送简洁版复盘摘要
# message工具发送到元宝
```

---

## 步骤8：结构化复盘数据导出（新增）

将今日复盘关键数据追加写入结构化 Excel 文件 `trading/复盘数据库.xlsx`。

**操作**：使用 `xlsx` 技能创建/追加 Excel 文件。

1. 读取 xlsx 技能（路径：`~/.qclaw/skills/xlsx/SKILL.md`）
2. 用 openpyxl（技能依赖）执行以下 Python 脚本：

```python
import openpyxl
from datetime import date
import json, os

FILE = '/Users/yuefengshen/.qclaw/workspace-1gwpiwf3hr163jz5/trading/复盘数据库.xlsx'
WS_PATH = '/Users/yuefengshen/.qclaw/workspace-1gwpiwf3hr163jz5'

headers = ['日期','维度','关注标的','代码','开盘价','收盘价','涨幅%','打分','竞价量比','涨停数','涨跌家数','情绪判定','命中']

today = date.today().strftime('%Y-%m-%d')

if os.path.exists(FILE):
    wb = openpyxl.load_workbook(FILE)
    ws = wb.active
else:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = '复盘记录'
    ws.append(headers)
    # 格式化表头
    from openpyxl.styles import Font, PatternFill
    for cell in ws[1]:
        cell.font = Font(bold=True)
        cell.fill = PatternFill(start_color='4472C4', end_color='4472C4', fill_type='solid')
        cell.font = Font(bold=True, color='FFFFFF')

# 去重检查：如果今日已有记录则更新，否则追加
existing_row = None
for row in ws.iter_rows(min_row=2, max_col=1):
    if row[0].value == today:
        existing_row = row[0].row
        break

# 从各数据源收集今日数据
row_data = [today]

# 维度（从 系统状态.json 读取）
try:
    with open(f'{WS_PATH}/trading/系统状态.json') as f:
        state = json.load(f)
    row_data.append(state.get('today', {}).get('dimension', ''))
except:
    row_data.append('')

# 关注标的（从 trading/关注股.md 提取第一行标的名和代码）
try:
    with open(f'{WS_PATH}/trading/关注股.md') as f:
        content = f.read()
    lines = [l for l in content.split('\n') if '|' in l and not l.strip().startswith('|--')]
    if len(lines) > 2:
        cells = [c.strip() for c in lines[2].split('|')]
        row_data.extend([cells[0] if len(cells)>0 else '', cells[1] if len(cells)>1 else ''])
    else:
        row_data.extend(['',''])
except:
    row_data.extend(['',''])

# 行情数据（留空由收盘任务填入）
row_data.extend(['','','','','','',''])

# 命中判定
row_data.append('')

if existing_row:
    for i, val in enumerate(row_data):
        ws.cell(row=existing_row, column=i+1, value=val)
    print(f'✅ 已更新第{existing_row}行（{today}）')
else:
    ws.append(row_data)
    print(f'✅ 已追加新行（{today}）')

wb.save(FILE)
```

3. 如果文件不存在会自动创建（含表头格式化）
4. 如果今日已有记录（同一日期），更新而非重复追加

> ⚡ 此步骤失败不应阻塞复盘流程，记录错误后继续。

---

## ❌ 错误处理与实时告警

**任何步骤失败，立即发送告警（不等待晚间修复）：**

| 步骤 | 失败表现 | 告警内容 |
|------|---------|----------|
| 读取复盘模板 | 文件不存在 | 【CRON_CLOSING_TASK 告警】复盘模板丢失 |
| 获取市场数据 | curl返回空 | 【CRON_CLOSING_TASK 告警】无法获取市场数据 |
**告警方式**：记录到 memory/YYYY-MM-DD.md 并通知用户

---

## 模拟交易：收盘更新市值 + 输出状态

```bash
python3 << 'PYEOF'
import sys, json, subprocess, re
sys.path.insert(0, "/Users/yuefengshen/.qclaw/workspace-1gwpiwf3hr163jz5/scripts")
from simulated_trading import update_positions, status

# 获取持仓股最新价
try:
    with open("/Users/yuefengshen/.qclaw/workspace-1gwpiwf3hr163jz5/trading/模拟持仓.json") as f:
        pos_data = json.load(f)
    codes = [p["code"] for p in pos_data["positions"]]
    if codes:
        q_list = [f"sh{c}" if c.startswith("6") else f"sz{c}" for c in codes]
        r = subprocess.run(["curl","-s","--max-time","10",f"https://qt.gtimg.cn/q={chr(44).join(q_list)}"], capture_output=True, timeout=12)
        raw = r.stdout
        for enc in ["gb2312","gbk","utf-8"]:
            try: txt = raw.decode(enc); break
            except: continue
        price_map = {}
        for line in txt.split(";"):
            m = re.search(r"v_\w+=\"([^"]*)\"", line)
            if m:
                vals = m.group(2).split("~")
                if len(vals) > 4 and vals[4]:
                    code = m.group(1)[2:]  # 去掉sh/sz前缀
                    price_map[code] = float(vals[4])  # vals[4]=今收盘价
        update_positions(price_map)
    print("\n" + "="*40)
    print("📊 模拟交易收盘状态")
    print("="*40)
    print(status())
except Exception as e:
    print(f"⚠️ 模拟交易更新失败: {e}")
PYEOF
```

## 模拟交易：卖点检测（止损/止盈）

收盘更新市值后，运行卖点检测器，自动触发止损/止盈：

```bash
python3 /Users/yuefengshen/.qclaw/workspace-1gwpiwf3hr163jz5/scripts/lobster_sellpoint_detector.py
```

**检测逻辑**（对齐lobster-rules.md v2.3 + 止盈体系）：
| 维度 | 逻辑 | 条件 |
|------|------|------|
| **1.0** | 硬止损 -5% / 时间止损(第3天未涨停) | 收盘价 < 买入价×0.95 |
| **2.0** | 硬止损 -7% | 收盘价 < 买入价×0.93 |
| **3.0** | 技术止损 MA5<MA10 | 均线死叉 |
| **全部** | 时间止损 | 持仓>5个交易日 |
| **1.0/2.0止盈** | 分时止盈（盘中执行，收盘复盘不做） | 盘中主高/次高判断 |
| **3.0止盈** | Tier-1退出观察 | 浮盈>10%+检查催化兑现/板块分化 |

**输出格式**：
- 🔴 卖出 XX(XXXXX): 止损：回撤-3.50% ≤ -3%
  - ✅ 卖出成功：XX(XXXXX) 卖出XX股@XX.XX 盈亏-XXX.XX(-X.XX%)

> ⚡ 此步骤失败不应阻塞复盘流程，记录错误后继续。

```bash
python3 << 'PYEOF'
try:
    import subprocess
    r = subprocess.run(['python3', '/Users/yuefengshen/.qclaw/workspace-1gwpiwf3hr163jz5/scripts/lobster_sellpoint_detector.py'], 
                      capture_output=True, timeout=30)
    output = r.stdout.decode('utf-8', 'replace')
    print(output)
    if r.returncode != 0:
        print(f"⚠️ 卖点检测失败: {r.stderr.decode('utf-8', 'replace')}")
except Exception as e:
    print(f"⚠️ 卖点检测异常: {e}")
PYEOF
```

---

## 五档数据分析（新增）

读取今日五档快照文件 `trading/five_level_snapshots/YYYYMMDD.jsonl`，分析盘中买卖力量变化。

```bash
python3 << 'PYEOF'
import json, os, datetime, collections

WS = '/Users/yuefengshen/.qclaw/workspace-1gwpiwf3hr163jz5'
today = datetime.date.today().strftime('%Y%m%d')
snap_file = f'{WS}/trading/five_level_snapshots/{today}.jsonl'

print('\n' + '='*40)
print('📊 五档数据分析')
print('='*40)

if not os.path.exists(snap_file):
    print(f'  ⚠️ 今日五档快照文件不存在: {snap_file}')
    print(f'  💡 五档采集cron将在下一交易日09:25启动')
    return

# 读取所有快照
records = []
with open(snap_file) as f:
    for line in f:
        line = line.strip()
        if line:
            try:
                records.append(json.loads(line))
            except: pass

if not records:
    print(f'  ⚠️ 快照文件为空')
    return

print(f'  共{len(records)}条快照，{len(set(r["code"] for r in records))}只股票')

# 按股票分组
by_code = collections.defaultdict(list)
for r in records:
    by_code[r['code']].append(r)

# 分析每只股票
for code, recs in sorted(by_code.items()):
    name = recs[0]['name']
    print(f'\n  📌 {name}({code})')
    
    # 开盘/收盘五档
    first = recs[0]
    last = recs[-1]
    
    # 买卖比趋势
    ratios = [r['ratio'] for r in recs]
    avg_ratio = sum(ratios)/len(ratios)
    
    # 涨停判定（买一量巨大）
    is_zt = any(r['bid'][0]['vol'] > 10000 for r in recs)
    
    # 跌停判定（卖一量巨大）
    is_dt = any(r['ask'][0]['vol'] > 10000 for r in recs)
    
    print(f'    首笔: {first["time"]} 价{first["price"]}({first["pct"]:+.2f}%) 买卖比{first["ratio"]:.2f}')
    print(f'    尾笔: {last["time"]} 价{last["price"]}({last["pct"]:+.2f}%) 买卖比{last["ratio"]:.2f}')
    print(f'    平均买卖比: {avg_ratio:.2f}', end='')
    
    if is_zt:
        print('  🔴涨停封板')
    elif is_dt:
        print('  🟢跌停')
    elif avg_ratio > 2:
        print('  ⚠️卖压重')
    elif avg_ratio < 0.5:
        print('  ✅买盘强')
    else:
        print('  ➡️平衡')
    
    # 价格区间
    prices = [r['price'] for r in recs]
    print(f'    价格区间: {min(prices):.2f} ~ {max(prices):.2f}')

print('\n' + '='*40)
print('✅ 五档分析完成')
PYEOF
```

> 💡 五档数据由「龙虾五档采集」cron（09:25触发，每分钟采集）提供。
> 若文件不存在，说明当日cron未运行（检查cron列表）。

---

- [ ] 已按复盘模板输出9个章节
- [ ] 已更新 `trading/选股历史.md`
- [ ] **已更新 `trading/催化日历.md`**（滚动归档+新催化追加）
- [ ] 已同步IMA知识库
- [ ] **已分析五档数据（盘中买卖力量）**
- [ ] 已发送消息给用户
- [ ] 已写入 `memory/YYYY-MM-DD.md`
- [ ] 已追加 `trading/复盘数据库.xlsx`

# 更新系统状态（供明日盘前3.0激活判断）
# BUG修复: 不再依赖last_updated计算yesterday.date，改用last_close_date
try:
    import datetime
    yesterday_state = {}
    state_path = f'{WS_PATH}/trading/系统状态.json'
    if os.path.exists(state_path):
        with open(state_path) as f:
            yesterday_state = json.load(f)
    
    # 上一交易日 = today - 1天（跳过周末自动处理）
    today_dt = datetime.date.today()
    prev_day = (today_dt - datetime.timedelta(days=1)).strftime('%Y-%m-%d')
    
    new_state = {
        '_meta': {'version': 2, 'purpose': '系统状态·统一文件'},
        'last_updated': today,
        'last_close_date': today,  # 今日收盘日期（用于明日盘前判断）
        'yesterday': {
            'up_count': yesterday_state.get('yesterday', {}).get('up_count', 0),  # 上上日的真实收盘数据
            'date': yesterday_state.get('last_close_date', prev_day)  # 上一实际收盘日
        },
        'today': {
            'up_count': up_count,
            'down_count': down_count,
            'zt_count': zt_count,
            'dt_count': dt_count,
            'dimension': emotion
        }
    }
    with open(state_path, 'w') as f:
        json.dump(new_state, f, ensure_ascii=False, indent=2)
    print(f"✅ 系统状态已更新: 昨{new_state['yesterday']['up_count']}({new_state['yesterday']['date']})→今{up_count}({today})")
except Exception as e:
    print(f"⚠️ 更新系统状态失败: {e}")

---

**任务版本**：v5（新增催化日历滚动更新）
**最后更新**：2026-05-20

---

## 最后步骤：回复用户（必须执行）

> **关键**：你已执行完所有步骤，生成了完整的收盘复盘报告
> **必须**：立即回复用户，将复盘报告完整发送给用户
> **禁止**：NO_REPLY、不回复、只写文件不推送
>
> 回复格式：
> ```
> 📊 龙虾收盘复盘 YYYY-MM-DD
> 
> [完整的9章节内容]
> ```

---

## 📎 任务反馈链 — 写入本任务结论

**任务执行完毕后，必须将关键结论追加写入 `trading/task-feedback-chain.md`**。

在文件末尾追加以下格式的内容（使用 edit_file 工具追加）：

```
### {任务名} ({HH:MM})
- **关键结论**：{1-3 条核心发现/修复/信号，每条一句话}
- **给下个任务**：{给下游任务的 1-2 条具体参考建议，如"关注 XX 板块""XX 参数需监控""上一次的 YY 建议已验证为有效/无效"}
```

**规则**：
- 任务名使用本文件标题中的人类可读名称（如"晚间要闻""盘前选股""盘中巡检"）
- 时间使用实际执行时间
- 关键结论只写本任务最重要的发现，不写流水账
- "给下个任务"必须是**可操作的参考**，下游任务真正能用上
