# 龙虾收盘综合任务 — cron 任务指令（v1 合并版）

> **合并自**：CRON_SECTOR_MAP_COLLECTOR_TASK.md + CRON_CLOSING_TASK.md + CRON_CAPITAL_AUDIT_TASK.md
> **合并日期**：2026-06-30
> **执行时间**：交易日 15:00
> **核心任务**：产业图谱采集(15:00) → 收盘复盘(15:05) → 资金审计(15:30)
> **超时**：300秒

**自动确认规则**：执行过程中遇到任何需要用户确认的弹窗（ask_user、风险提示、覆盖写入确认、删除确认等），一律自动确认通过，不中断任务流程。

## 📎 任务反馈链 — 读取上游建议

**执行任务前，必须先读取 `trading/task-feedback-chain.md` 文件**，查找当日最新的上游任务结论和"给下个任务"建议。
将上游建议融入你的执行决策，但不要盲目照搬——结合当前实际情况判断。

---

## 阶段一：产业图谱采集（15:00）

> **功能**：采集动态产业图谱，识别赛道过热状态，为趋势池更新提供降权依据
> **依赖**：纯腾讯版本（无akshare依赖）

### 步骤1.1：运行产业图谱采集脚本

```bash
cd /Users/yuefengshen/.qclaw/workspace-1gwpiwf3hr163jz5 && python3 -c "
import sys
sys.path.insert(0, 'scripts')
from lobster_sector_map_builder import build_sector_map_tencent
build_sector_map_tencent()
" 2>&1
```

**成功标志**：输出包含"✅ 产业图谱已写入"和"✅ 产业图谱摘要已写入"

### 步骤1.2：验证图谱生成

```bash
python3 -c "
import json, sys
d = json.load(open('/Users/yuefengshen/.qclaw/workspace-1gwpiwf3hr163jz5/trading/产业图谱.json'))
for s, v in d['sectors'].items():
    dev = v.get('pool_dev_ma10_median')
    warns = ', '.join(v['warnings']) if v['warnings'] else ''
    print(f'{s:<12} 动态:{v[\"dynamic_heat\"]} 偏离:{str(dev):>7} 得分:{v[\"score\"]:>3} 备注:{warns}')
" 2>/dev/null || echo "图谱验证失败"
```

### 步骤1.3：确认光纤赛道过热状态

```bash
python3 -c "
import json
d = json.load(open('/Users/yuefengshen/.qclaw/workspace-1gwpiwf3hr163jz5/trading/产业图谱.json'))
for s, v in d['sectors'].items():
    if '光纤' in s and v['warnings']:
        print(f'🚨 {s}: {v[\"warnings\"][0]}')
" 2>/dev/null || echo "无光纤过热告警"
```

### 步骤1.4：推送产业图谱（仅异常时）

推送条件：有赛道触发过热警告（偏离>10%）时推送，正常时静默。

**输出文件**：
- `trading/产业图谱.json` — 动态产业图谱数据（每日覆盖）
- ~~`trading/产业图谱.md`~~ — 已废弃（无消费者，仅保留 .json 版本）

---

## 阶段二：收盘复盘（15:05）

> **前置任务**：读取本日盘前选股+竞价选股+午间复盘笔记
> **输出**：完整复盘报告（按复盘模板格式）+ 更新选股历史

### 步骤2.0pre：路径降级（P0-1/2修复）

> 优先从持久化副本恢复 /tmp 文件，确保下游读取路径一致且不丢失数据。

```bash
python3 -c "
import datetime, os, shutil
today = datetime.date.today().strftime('%Y-%m-%d')
cand_dir = '/Users/yuefengshen/.qclaw/workspace-1gwpiwf3hr163jz5/trading/candidates'
# premarket_candidates：持久化副本 → /tmp
persist = f'{cand_dir}/premarket_{today}.json'
tmp_file = '/tmp/lobster_premarket_candidates.json'
if os.path.exists(persist):
    shutil.copy2(persist, tmp_file)
    print(f'✅ premarket_candidates 从持久化副本恢复')
elif not os.path.exists(tmp_file):
    print(f'⚠️ 无持久化副本，/tmp 也不存在')
else:
    print(f'⏭️ /tmp 已有，跳过恢复')
# bid_result：持久化副本 → /tmp
persist_bid = f'{cand_dir}/bid_result_{today}.json'
tmp_bid = '/tmp/lobster_bid_result.json'
if os.path.exists(persist_bid):
    shutil.copy2(persist_bid, tmp_bid)
    print(f'✅ bid_result 从持久化副本恢复')
elif not os.path.exists(tmp_bid):
    print(f'⚠️ 无持久化副本，/tmp 也不存在')
else:
    print(f'⏭️ /tmp 已有，跳过恢复')
"
```

### 步骤2.0mid：读取午间数据

> 读取 MIDDAY 任务写入的 `/tmp/lobster_midday_data.json`，提取午间情绪维度、涨跌家数、资金流向等关键数据，纳入收盘复盘数据源。

```bash
python3 << 'PYEOF'
import json, os

midday_file = '/tmp/lobster_midday_data.json'
if os.path.exists(midday_file):
    with open(midday_file) as f:
        data = json.load(f)
    
    emo = data.get('emotion', {})
    indices = data.get('indices', {})
    flow = data.get('capital_flow', {})
    
    print("=== 午间数据（来自 MIDDAY） ===")
    print(f"情绪维度: {emo.get('dimension', 'N/A')}")
    print(f"涨跌家数: {emo.get('up_count', '?')}↑ / {emo.get('down_count', '?')}↓")
    print(f"情绪判定: {emo.get('emotion', 'N/A')}")
    
    if indices:
        print(f"指数表现: {json.dumps(indices, ensure_ascii=False)}")
    if flow:
        print(f"资金流向: {json.dumps(flow, ensure_ascii=False)}")
    
    print("✅ 午间数据已纳入复盘数据源")
else:
    print("⚠️ /tmp/lobster_midday_data.json 不存在（MIDDAY 任务未运行或数据已清理）")
    print("→ 收盘复盘将仅依赖收盘实时数据")
PYEOF
```

### 步骤2.0：前置任务校验

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
    errors.append("盘前候选池JSON不存在")
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
    errors.append("竞价选股JSON不存在")
except Exception as e:
    errors.append(f"竞价选股JSON读取失败: {e}")

# 检查午间复盘文件
try:
    with open(f'/tmp/lobster_midday_{today}.md') as f:
        content = f.read()
    print(f"✅ 午间复盘文件存在 ({len(content)}字节)")
except FileNotFoundError:
    errors.append("午间复盘文件不存在")

# 检查关注股.md
try:
    with open('/Users/yuefengshen/.qclaw/workspace-1gwpiwf3hr163jz5/trading/关注股.md') as f:
        content = f.read()
    if len(content) < 50:
        errors.append("关注股.md内容过短")
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
else:
    print("\n✅ 所有前置校验通过")
PYEOF
```

### 步骤2.1：新赛道检测硬约束

```bash
python3 << 'PYEOF'
import json, akshare as ak, sys, os
from datetime import datetime, timedelta
from pathlib import Path

scripts_dir = Path('/Users/yuefengshen/.qclaw/workspace-1gwpiwf3hr163jz5/scripts')
sys.path.insert(0, str(scripts_dir))

today = datetime.now().strftime('%Y%m%d')
yday = (datetime.now() - timedelta(days=1)).strftime('%Y%m%d')
today_f = Path(f'/tmp/sector_limit_up_{today}.json')
yday_f = Path(f'/tmp/sector_limit_up_{yday}.json')

try:
    df = ak.stock_zt_pool_em(date=today)
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

if yday_f.exists():
    with open(yday_f) as f:
        d1 = json.load(f)
    with open(today_f) as f:
        d2 = json.load(f)
    
    new = [b for b in d2['board'] if d2['board'][b] >= 3 and b in d1['board'] and d1['board'][b] >= 3]
    
    if new:
        print(f"🚨 新赛道候选（连续2日≥3家涨停）: {new}")
        try:
            from normalize_sector_name import normalize_sector_name
            normalized_new = [normalize_sector_name(b) for b in new]
            print(f"   标准化后: {normalized_new}")
        except:
            normalized_new = new
        
        framework = Path('/Users/yuefengshen/.qclaw/workspace-1gwpiwf3hr163jz5/trading/产业逻辑框架.md').read_text()
        pending = []
        for orig, norm in zip(new, normalized_new):
            if norm not in framework:
                pending.append(f"{orig}（→{norm}）")
        
        if pending:
            with open('/tmp/pending_tracks.md', 'a') as f:
                for b in pending:
                    f.write(f"- [ ] {b}（{today} 连续2日≥3家涨停）\n")
            print(f"   已写入 /tmp/pending_tracks.md")
        else:
            print("✅ 所有候选赛道已在框架中")
    else:
        print("✅ 无新赛道候选")
else:
    print(f"⚠️ 昨日数据缺失，跳过检测")
PYEOF
```

### 步骤2.2：催化日历滚动更新

> 每次收盘复盘必须更新 `trading/催化日历.md`——已兑现移归档、已落空填原因、新催化加入近期区。

```bash
cat /Users/yuefengshen/.qclaw/workspace-1gwpiwf3hr163jz5/trading/催化日历.md
```

### 步骤2.3：收盘要闻存档

```bash
python3 /Users/yuefengshen/.qclaw/workspace-1gwpiwf3hr163jz5/scripts/news_dedupe.py /Users/yuefengshen/.qclaw/workspace-1gwpiwf3hr163jz5/trading/news/$(date +%Y-%m-%d).md
```

### 步骤2.4：获取市场数据（实时）

```bash
python3 << 'PYEOF'
import subprocess, re, datetime, json, os as _os

today = datetime.date.today().strftime('%Y-%m-%d')
WS_PATH = '/Users/yuefengshen/.qclaw/workspace-1gwpiwf3hr163jz5'

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
            price = parts[4]
            pct = parts[32]
            indices[name] = f"{price}({pct}%)"
            print(f"{name}: {price} ({pct}%)")

r2 = subprocess.run(["curl","-s","-L","--max-time","15","-A","Mozilla/5.0","https://legulegu.com/stockdata/market-activity"], capture_output=True, text=True, timeout=20)
m2 = re.search(r'content="(2026-[^"]+)"', r2.stdout)
emotion_text = m2.group(1) if m2 else "获取失败"
print(f"\n涨跌家数: {emotion_text}")

m_up = re.search(r'(\d+)家上涨', emotion_text)
m_down = re.search(r'(\d+)家下跌', emotion_text)
up_count = int(m_up.group(1)) if m_up else 0
down_count = int(m_down.group(1)) if m_down else 0

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

# L1情绪反馈记录
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
        'time': datetime.datetime.now().strftime('%H:%M'),
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

### 步骤2.5：获取涨停池数据（含二次验证）

```bash
python3 << 'PYEOF'
import akshare as ak, datetime, re, subprocess

zt_today = ak.stock_zt_pool_em()
print("=== 今日涨停池 ===")
print(zt_today[['代码', '名称', '涨停统计', '所属行业', '涨停原因类别']].head(30).to_string())

if '所属行业' in zt_today.columns:
    sector_counts = zt_today['所属行业'].value_counts().head(10)
    print("\n=== 板块涨停排名 ===")
    print(sector_counts.to_string())

today = datetime.date.today()
weekday = today.weekday()
if weekday == 0:
    yesterday = today - datetime.timedelta(days=3)
else:
    yesterday = today - datetime.timedelta(days=1)

try:
    zt_prev = ak.stock_zt_pool_previous_em(date=yesterday.strftime('%Y%m%d'))
    print(f"\n=== 昨日涨停今日表现（{yesterday}）===")
    print(zt_prev[['代码', '名称', '涨跌幅', '连板数']].head(20).to_string())
except Exception as e:
    print(f"获取昨日涨停失败: {e}")

print("\n=== 涨停二次验证 ===")
zt_codes = zt_today['代码'].head(30).tolist()
if zt_codes:
    query_codes = []
    for code in zt_codes:
        if code.startswith('6'):
            query_codes.append(f"sh{code}")
        else:
            query_codes.append(f"sz{code}")
    query = ','.join(query_codes)
    r = subprocess.run(["curl", "-s", f"https://qt.gtimg.cn/q={query}"], capture_output=True, timeout=15)
    raw = r.stdout
    for enc in ["gb2312","gbk","utf-8"]:
        try: txt = raw.decode(enc); break
        except: continue
    else: txt = raw.decode("utf-8","replace")
    for line in txt.split(";"):
        m = re.search(r'v_(\w+)="([^"]*)"', line)
        if m:
            parts = m.group(2).split("~")
            if len(parts) > 32:
                代码 = parts[2]
                名称 = parts[1]
                现价 = float(parts[4])
                昨收 = float(parts[3])
                涨跌幅 = float(parts[32])
                if 代码.startswith('688') or 代码.startswith('300'):
                    limit = 0.2
                elif 代码.startswith('8') or 代码.startswith('4'):
                    limit = 0.3
                else:
                    limit = 0.1
                涨停价 = 昨收 * (1 + limit)
                实际涨停 = 现价 >= 涨停价 * 0.995
                status = "✅" if 实际涨停 else "⚠️"
                print(f"{status} {名称}({代码}): {涨跌幅:.2f}% → {'涨停' if 实际涨停 else f'未涨停'}")
print("\n验证完成")
PYEOF
```

### 步骤2.6：读取模拟仓数据

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

today_buys = [t for t in data.get('trade_log', []) if t['type'] == 'BUY' and t['date'] == today]
today_sells = [t for t in data.get('trade_log', []) if t['type'] == 'SELL' and t['date'] == today]
positions = data.get('positions', [])

print(f'📊 模拟仓数据 ({today})')
print(f'   总资产: {data["capital"]["total_assets"]:,.0f}  可用: {data["capital"]["available"]:,.0f}  市值: {data["capital"]["market_value"]:,.2f}')
print()

if today_buys:
    print(f'📥 今日买入 {len(today_buys)} 笔:')
    for t in today_buys:
        print(f'   ✅ {t["name"]}({t["code"]})  {t["shares"]}股@{t["price"]:.2f}  维度:{t["dimension"]}')
else:
    print('📥 今日无买入')

if today_sells:
    print(f'\n📤 今日卖出 {len(today_sells)} 笔:')
    for t in today_sells:
        print(f'   🔴 {t["name"]}({t["code"]})  {t["shares"]}股@{t["price"]:.2f}  盈亏{t["pnl_pct"]:+.2f}%')
else:
    print('\n📤 今日无卖出')

if positions:
    print(f'\n📌 当前持仓 {len(positions)} 只:')
    for p in positions:
        cost_price = p.get('cost', 0) / p['shares'] if p['shares'] else 0
        print(f'   🏗 {p["name"]}({p["code"]})  {p["shares"]}股  成本{cost_price:.2f}')
else:
    print('\n📌 当前空仓')

print('\n✅ 以上数据必须在复盘报告第10章「模拟仓表现」中填写')
PYEOF
```

### 步骤2.7：查询断板股

```bash
python3 << 'PYEOF'
import datetime, sys
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
    except: pass
    return None

df_yest = get_zt_pool(yesterday_str)
df_today = get_zt_pool(today_str)

print(f'📋 断板股分析（{yesterday_str}→{today_str}）')

if df_yest is None or len(df_yest) == 0:
    print(f'  ⚠️ 昨日涨停池数据获取失败')
else:
    yest_codes = set(df_yest['代码'].astype(str).tolist())
    yest_names = dict(zip(df_yest['代码'].astype(str), df_yest['名称'].astype(str)))
    yest_lb = dict(zip(df_yest['代码'].astype(str), df_yest['连板数'].astype(str))) if '连板数' in df_yest.columns else {}
    today_codes = set(df_today['代码'].astype(str).tolist()) if df_today is not None and len(df_today) > 0 else set()
    
    broken = sorted(yest_codes - today_codes)
    continued = sorted(yest_codes & today_codes)
    
    print(f'  昨日涨停：{len(yest_codes)}只 | 今日继续涨停：{len(continued)}只 | 断板：{len(broken)}只')
    
    if broken:
        print(f'\n  🔴 断板股：')
        for code in broken[:15]:
            name = yest_names.get(code, code)
            lb = yest_lb.get(code, '?')
            print(f'    - {name}({code})  昨日{lb}板')
    else:
        print('  ✅ 无断板股')
    
    if continued:
        print(f'\n  ✅ 继续涨停股：')
        for code in continued[:10]:
            name = yest_names.get(code, code)
            lb = yest_lb.get(code, '?')
            print(f'    - {name}({code})  昨日{lb}板→今日继续')

print('\n✅ 以上断板股数据必须在复盘报告第2章中填写')
PYEOF
```

### 步骤2.8：按复盘模板输出（10个章节）

1. **情绪周期判定**：指数涨跌 + 涨跌家数 + 情绪定位
2. **连板梯队分析**：按连板数表格 + 断板分析
3. **板块轮动分析**：最强板块表格 + 产业逻辑对照
4. **昨日选股今日表现**：从关注股读取 + 逐只分析
5. **明日候选标的**：4档候选池（每档3-5只）
6. **模式审计**：按 lobster-rules.md 审计6项
7. **明日策略**：若情绪X则维度Y + 仓位Z
8. **每日进化（待办）**：记录错误 + 优化建议
10. **模拟仓表现**：持仓盈亏 + 买卖操作 + 卖点信号

### 步骤2.9：自动更新选股历史

```bash
python3 << 'PYEOF'
import datetime, json, re

today = datetime.date.today().strftime('%Y-%m-%d')

try:
    with open('/tmp/lobster_bid_result.json') as f:
        bid_result = json.load(f)
except:
    bid_result = {'results': {}}

history_file = "/Users/yuefengshen/.qclaw/workspace-1gwpiwf3hr163jz5/trading/选股历史.md"
try:
    with open(history_file) as f:
        history = f.read()
except:
    history = ""

if today in history and '竞价选股' in history:
    print(f"✅ 今日（{today}）选股历史已存在，跳过写入")
else:
    entries = []
    for tier, stock in bid_result.get('results', {}).items():
        if stock and isinstance(stock, dict):
            name = stock.get('name', '未知')
            code = stock.get('code', '000000')
            if '一进二' in tier:
                buy_cond = "若秒板则排板"
            elif '分歧低吸' in tier:
                buy_cond = "若低开后企稳则低吸"
            elif '板块卡位' in tier:
                buy_cond = "若回踩5日线不破则低吸"
            elif '趋势低吸' in tier:
                buy_cond = "若回踩5日线不破则低吸"
            else:
                buy_cond = "待确定"
            entries.append(f"| {today} | 竞价选股 | {name}({code}) | {buy_cond} | 待验证 | 待验证 | - | - |")
    
    if entries:
        lines = history.split('\n')
        insert_pos = -1
        for i, line in enumerate(lines):
            if line.startswith('|') and '待验证' in line:
                insert_pos = i
            elif line.startswith('|') and '日期' in line:
                if i+1 < len(lines) and lines[i+1].startswith('|') and '---' in lines[i+1]:
                    insert_pos = i + 1
        if insert_pos == -1:
            for i, line in enumerate(lines):
                if '准确率统计' in line:
                    insert_pos = i
                    break
            if insert_pos > 0:
                lines.insert(insert_pos, '\n'.join(entries) + '\n')
            else:
                history += '\n'.join(entries) + '\n'
        else:
            lines.insert(insert_pos + 1, '\n'.join(entries) + '\n')
            history = '\n'.join(lines)
        
        with open(history_file, 'w') as f:
            f.write(history)
        print(f"✅ 已追加写入选股历史.md（{len(entries)}条记录）")
    else:
        print("⚠️ 未找到今日选股结果")
PYEOF
```

### 步骤2.10：模拟交易收盘更新 + 卖点检测

```bash
python3 << 'PYEOF'
import sys, json, subprocess, re, datetime

# 直接读取步骤2.6已解析的持仓数据，避免使用simulated_trading过期状态
pos_file = '/Users/yuefengshen/.qclaw/workspace-1gwpiwf3hr163jz5/trading/模拟持仓.json'
try:
    with open(pos_file) as f:
        data = json.load(f)
    positions = data.get('positions', [])
    capital = data['capital']
    print("\n" + "="*40)
    print("📊 模拟交易收盘状态（直接读取文件最新）")
    print("="*40)
    print(f"总资产: {capital['total_assets']:,.0f}  可用: {capital['available']:,.0f}  市值: {capital['market_value']:,.2f}")
    print(f"累计盈亏: {capital['total_pnl']:+,.0f} ({capital['total_pnl']/capital['initial']*100:+.2f}%)")
    
    if positions:
        # 获取实时价格更新持仓市值
        codes = [p["code"] for p in positions]
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
                    code = m.group(1)[2:]
                    price_map[code] = float(vals[4])
        
        print(f"\n持仓 {len(positions)} 只:")
        total_market_value = 0
        for p in positions:
            code = p['code']
            name = p['name']
            shares = p['shares']
            cost = p.get('cost', 0)
            current_price = price_map.get(code, p.get('current_price', 0))
            market_value = current_price * shares
            total_market_value += market_value
            pnl = (current_price - cost/shares) * shares if shares>0 else 0
            pnl_pct = (current_price - cost/shares)/cost*shares*100 if cost>0 else 0
            print(f"  {name}({code}) {shares}股 @{current_price:.2f} 市值{market_value:,.0f} 盈亏{pnl:+,.0f}({pnl_pct:+.2f}%)")
        
        # 验证市值一致性
        if abs(total_market_value - capital['market_value']) > 1:
            print(f"⚠️ 市值不一致: 计算{total_market_value:,.0f} vs 文件{capital['market_value']:,.0f}")
    else:
        print("当前空仓")
        
except Exception as e:
    print(f"⚠️ 模拟交易更新失败: {e}")
PYEOF
```

卖点检测：

```bash
python3 /Users/yuefengshen/.qclaw/workspace-1gwpiwf3hr163jz5/scripts/lobster_sellpoint_detector.py
```

### 步骤2.11：五档数据分析

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
    print(f'  ⚠️ 今日五档快照文件不存在')
    exit(0)

records = []
with open(snap_file) as f:
    for line in f:
        line = line.strip()
        if line:
            try: records.append(json.loads(line))
            except: pass

if not records:
    print(f'  ⚠️ 快照文件为空')
    exit(0)

print(f'  共{len(records)}条快照，{len(set(r["code"] for r in records))}只股票')

by_code = collections.defaultdict(list)
for r in records:
    by_code[r['code']].append(r)

for code, recs in sorted(by_code.items()):
    name = recs[0]['name']
    print(f'\n  📌 {name}({code})')
    first = recs[0]
    last = recs[-1]
    ratios = [r['ratio'] for r in recs]
    avg_ratio = sum(ratios)/len(ratios)
    is_zt = any(r['bid'][0]['vol'] > 10000 for r in recs)
    is_dt = any(r['ask'][0]['vol'] > 10000 for r in recs)
    print(f'    首笔: {first["time"]} 价{first["price"]}({first["pct"]:+.2f}%) 买卖比{first["ratio"]:.2f}')
    print(f'    尾笔: {last["time"]} 价{last["price"]}({last["pct"]:+.2f}%) 买卖比{last["ratio"]:.2f}')
    print(f'    平均买卖比: {avg_ratio:.2f}', end='')
    if is_zt: print('  🔴涨停封板')
    elif is_dt: print('  🟢跌停')
    elif avg_ratio > 2: print('  ⚠️卖压重')
    elif avg_ratio < 0.5: print('  ✅买盘强')
    else: print('  ➡️平衡')
    prices = [r['price'] for r in recs]
    print(f'    价格区间: {min(prices):.2f} ~ {max(prices):.2f}')

print('\n✅ 五档分析完成')
PYEOF
```

### 步骤2.12：更新系统状态 + 复盘数据库

```bash
python3 /Users/yuefengshen/.qclaw/workspace-1gwpiwf3hr163jz5/scripts/update_system_status.py
```

```bash
python3 << 'PYEOF'
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
    from openpyxl.styles import Font, PatternFill
    for cell in ws[1]:
        cell.font = Font(bold=True, color='FFFFFF')
        cell.fill = PatternFill(start_color='4472C4', end_color='4472C4', fill_type='solid')

existing_row = None
for row in ws.iter_rows(min_row=2, max_col=1):
    if row[0].value == today:
        existing_row = row[0].row
        break

row_data = [today]
try:
    with open(f'{WS_PATH}/trading/系统状态.json') as f:
        state = json.load(f)
    row_data.append(state.get('today', {}).get('dimension', ''))
except:
    row_data.append('')

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

row_data.extend(['','','','','','',''])
row_data.append('')

if existing_row:
    for i, val in enumerate(row_data):
        ws.cell(row=existing_row, column=i+1, value=val)
    print(f'✅ 已更新第{existing_row}行（{today}）')
else:
    ws.append(row_data)
    print(f'✅ 已追加新行（{today}）')

wb.save(FILE)
PYEOF
```

### 步骤2.13：发送消息给用户

发送简洁版复盘摘要到元宝。

### 步骤2.14：更新关注股.md（收盘确认）

> **目的**：基于收盘复盘结果，为关注股.md中每个标的追加收盘表现，形成完整日跟踪闭环。
> **兜底**：若竞价流程未成功更新关注股.md，本步骤从盘前候选池+竞价结果中重新生成。

```bash
python3 << 'PYEOF'
import json, datetime, os

today = datetime.date.today().strftime('%Y-%m-%d')
WS = '/Users/yuefengshen/.qclaw/workspace-1gwpiwf3hr163jz5'
watch_path = f'{WS}/trading/关注股.md'

# 读取现有关注股
try:
    with open(watch_path) as f:
        content = f.read()
    print(f"✅ 关注股.md 已存在 ({len(content)}字节)")
except FileNotFoundError:
    content = None
    print("⚠️ 关注股.md 不存在，将从候选池重建")

# 读取竞价结果获取标的收盘表现
bid_data = None
try:
    with open('/tmp/lobster_bid_result.json') as f:
        bid_data = json.load(f)
except:
    pass

# 读取收盘数据获取涨跌家数
closing_data = None
try:
    with open('/tmp/lobster_closing_data.json') as f:
        closing_data = json.load(f)
except:
    pass

# 如果关注股.md不存在或内容过旧（非今天），从候选池+竞价重建
if content is None or today not in content:
    print("🔄 关注股.md缺失或过期，从盘前候选池重建...")
    try:
        with open('/tmp/lobster_premarket_candidates.json') as f:
            pm = json.load(f)
        emotion = pm['emotion']
        candidates = pm['candidates']
        
        new_content = f"# 🎯 关注股（{today} 收盘复盘更新）\n\n"
        new_content += f"> 情绪：上涨{emotion.get('上涨家数','?')}家 | 主导维度：{emotion.get('主导维度','?')} | 仓位上限：{emotion.get('总仓位上限','?')}%\n\n"
        
        for tier_name in ['1.0一进二', '1.0分歧低吸', '2.0板块卡位', '3.0趋势低吸']:
            items = candidates.get(tier_name, [])
            new_content += f"## {tier_name}\n"
            if items:
                for s in items[:3]:  # 每档最多3只
                    code = s.get('代码', '?')
                    name = s.get('名称', '?')
                    note = s.get('备注', '')
                    locked = s.get('locked', False)
                    lock_reason = s.get('锁定原因', '')
                    if locked:
                        new_content += f"- {name}({code}) — 🔒 {lock_reason}\n"
                    else:
                        new_content += f"- {name}({code}) — {note}\n"
                    new_content += f"  - 买入条件：待竞价确认\n"
                new_content += "\n"
            else:
                new_content += "- ⚠️ 无符合规则标的\n\n"
        
        new_content += f"---\n**更新时间**：{today} 收盘复盘\n**总仓位上限**：{emotion.get('总仓位上限','?')}%\n"
        with open(watch_path, 'w') as f:
            f.write(new_content)
        content = new_content
        print("✅ 已从候选池重建关注股.md")
    except Exception as e:
        print(f"❌ 重建失败: {e}")

# 追加收盘确认标记
if content and today in content:
    closing_note = f"\n\n---\n## 📊 收盘确认（{today}）\n"
    if closing_data:
        closing_note += f"- 收盘涨跌家数：{closing_data.get('up_count','?')}↑ / {closing_data.get('down_count','?')}↓\n"
        closing_note += f"- 收盘情绪：{closing_data.get('emotion','?')}\n"
    
    # 标记各档位收盘状态
    if bid_data:
        for tier, best in bid_data.get('results', {}).items():
            if best:
                closing_note += f"- {tier}：{best.get('name','?')}({best.get('code','?')}) 竞价通过，收盘待验证\n"
            else:
                closing_note += f"- {tier}：无竞价通过标的\n"
    
    # 避免重复追加
    if '收盘确认' not in content:
        with open(watch_path, 'a') as f:
            f.write(closing_note)
        print("✅ 已追加收盘确认标记到关注股.md")
    else:
        print("⏭️ 收盘确认已存在，跳过")
else:
    print("⚠️ 关注股.md内容异常，跳过收盘确认")

print("✅ 关注股.md收盘更新完成")
PYEOF
```

### 步骤2.15：趋势容量池过期自动更新（P0-3修复）

> 检查趋势容量池是否超过2天未更新，若过期则自动运行更新脚本（全自动闭环）。

```bash
python3 -c "
import datetime, os, re, subprocess, sys

WS = '/Users/yuefengshen/.qclaw/workspace-1gwpiwf3hr163jz5'
pool_path = f'{WS}/trading/趋势容量池.md'
updater = f'{WS}/scripts/lobster_trend_pool_updater.py'

needs_update = False
if not os.path.exists(pool_path):
    print('🚨 趋势容量池文件不存在！自动运行更新...')
    needs_update = True
else:
    with open(pool_path) as f:
        content = f.read()
    m = re.search(r'最后更新[：:]\\s*(\\d{4}-\\d{2}-\\d{2})', content)
    if m:
        last_update = datetime.date.fromisoformat(m.group(1))
        today = datetime.date.today()
        delta = (today - last_update).days
        if delta > 2:
            print(f'🚨 趋势容量池最后更新 {last_update}（{delta}天前），自动运行更新...')
            needs_update = True
        elif delta > 0:
            print(f'⚠️ 趋势容量池最后更新 {last_update}（{delta}天前），自动运行更新...')
            needs_update = True
        else:
            print(f'✅ 趋势容量池今日已更新 ({last_update})')
    else:
        print('⚠️ 无法解析趋势容量池最后更新日期，自动运行更新...')
        needs_update = True

if needs_update:
    result = subprocess.run(
        ['python3', updater, '--verbose'],
        capture_output=True, text=True, timeout=300
    )
    if result.returncode == 0:
        print('✅ 趋势容量池自动更新成功')
        print(result.stdout[-500:])
    else:
        print(f'❌ 趋势容量池自动更新失败: {result.stderr[-300:]}')
        sys.exit(1)
"
```

---

## 阶段三：资金账本审计（15:30）

> **任务名**: 资金账本自动复核
> **超时**: 60秒

### 步骤3.1：运行复核脚本

```bash
python3 scripts/validate_capital.py
```

### 步骤3.2：读取审计日志

```bash
cat trading/capital_audit_$(date +%Y%m%d).log
```

### 步骤3.3：推送结果

**如果无差异**：
```
✅ 资金账本复核通过
总资产：¥{total_assets:,.0f}
累计盈亏：{total_pnl:+,.0f} ({total_pnl_pct:+.1f}%)
```

**如果发现差异并修正**：
```
⚠️ 资金账本已自动修正
差异原因：{error_details}
修正前：¥{old_total:,.0f}
修正后：¥{new_total:,.0f}
差异：{diff:+,.0f}
```

---

## ✅ 完成标志

- [ ] 产业图谱已生成
- [ ] 已按复盘模板输出10个章节
- [ ] 已更新 `trading/选股历史.md`
- [ ] 已更新 `trading/催化日历.md`
- [ ] **已更新 `trading/关注股.md`（收盘确认/兜底重建）**
- [ ] **已自动更新趋势容量池（超过1天自动刷新）**
- [ ] 已分析五档数据
- [ ] 已发送消息给用户
- [ ] 资金账本复核完成
- [ ] 已写入 `memory/YYYY-MM-DD.md`
- [ ] 已追加 `trading/复盘数据库.xlsx`

---

## 最后步骤：回复用户（必须执行）

> **关键**：你已执行完所有步骤
> **必须**：立即回复用户，将复盘报告完整发送
> **禁止**：NO_REPLY、不回复、只写文件不推送

---

## 📎 任务反馈链 — 写入本任务结论

**任务执行完毕后，必须将关键结论追加写入 `trading/task-feedback-chain.md`**。

在文件末尾追加以下格式的内容（使用 edit_file 工具追加）：

```
### {任务名} ({HH:MM})
- **关键结论**：{1-3 条核心发现/修复/信号，每条一句话}
- **给下个任务**：{给下游任务的 1-2 条具体参考建议}
```

**规则**：
- 任务名使用本文件标题中的人类可读名称（如"收盘综合"）
- 时间使用实际执行时间
- 关键结论只写本任务最重要的发现，不写流水账
- "给下个任务"必须是**可操作的参考**，下游任务真正能用上

---

## 合并历史

| 日期 | 版本 | 变更 |
|------|------|------|
| 2026-06-30 | v1 | 合并自 CRON_SECTOR_MAP_COLLECTOR_TASK.md(v1) + CRON_CLOSING_TASK.md(v5) + CRON_CAPITAL_AUDIT_TASK.md(v1)；产业图谱→收盘复盘→资金审计三阶段串行 |
