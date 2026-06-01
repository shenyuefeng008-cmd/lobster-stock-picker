# 龙虾卖点监控 — cron 任务指令（v3 — 含分时止盈+Tier-1退出）

> **频率**：每30分钟（9:30-11:30, 13:00-14:30）+ 尾盘14:50
> **超时**：120秒
> **核心**：持仓检测 → 分时止盈(1.0/2.0) / 止损(分维度) / Tier-1退出(3.0) → 自动卖出

---

## 步骤1：读取持仓股列表（从模拟持仓.json）

```bash
python3 << 'PYEOF'
import json, sys

POSITION_FILE = "/Users/yuefengshen/.qclaw/workspace-1gwpiwf3hr163jz5/trading/模拟持仓.json"

try:
    with open(POSITION_FILE) as f:
        data = json.load(f)
    
    positions = data.get('positions', [])
    
    if positions:
        print(f"✅ 持仓股：{len(positions)}只")
        for p in positions:
            t1_tag = " 🔒T+1" if not p.get('can_sell') else ""
            print(f"  - {p['name']}({p['code']}) 买入{p['buy_price']} 成本{p['cost']:.0f}{t1_tag}")
    else:
        print("📋 无持仓，无需监控")
        sys.exit(0)
    
    # 保存供后续用
    with open("/tmp/lobster_positions.json", "w") as f:
        json.dump(positions, f, ensure_ascii=False, indent=2)
except FileNotFoundError:
    print("⚠️ 模拟持仓.json 不存在")
    sys.exit(0)
except Exception as e:
    print(f"⚠️ 读取持仓失败: {e}")
    sys.exit(0)
PYEOF
```

---

## 步骤2：获取持仓股实时行情 + 均线数据

```bash
python3 << 'PYEOF'
import json, subprocess, re, datetime, sys

# 读取持仓
try:
    with open("/tmp/lobster_positions.json") as f:
        positions = json.load(f)
except:
    print("⚠️ 无持仓数据")
    sys.exit(0)

if not positions:
    print("暂无持仓，无需监控")
    sys.exit(0)

# 获取实时行情
codes = [p['code'] for p in positions]
q_list = [f"sh{c}" if c.startswith('6') else f"sz{c}" for c in codes]
q_str = ",".join(q_list)

r = subprocess.run(["curl","-s","--max-time","10",f"https://qt.gtimg.cn/q={q_str}"], capture_output=True, timeout=12)
raw = r.stdout
for enc in ["gb2312","gbk","utf-8"]:
    try: txt = raw.decode(enc); break
    except: continue
else: txt = raw.decode("utf-8","replace")

# 解析行情
quotes = {}
for line in txt.split(";"):
    m = re.search(r'v_(\w+)="([^"]*)"', line)
    if m:
        p = m.group(2).split("~")
        if len(p) > 34:
            code = m.group(1)[2:]
            quotes[code] = {
                "name": p[1],
                "price": float(p[4]) if p[4] else 0,  # p[4]=当前价, p[3]=昨收
                "pct": float(p[32]) if p[32] else 0,
                "high": float(p[33]) if p[33] else 0,
                "low": float(p[34]) if p[34] else 0,
                "volume": int(p[6]) if p[6] else 0,
                "amount": float(p[37]) if len(p) > 37 else 0
            }

# 获取均线数据（akshare）
try:
    import akshare as ak
    for p in positions:
        code = p['code']
        if code not in quotes:
            continue
        
        try:
            df = ak.stock_zh_a_hist(symbol=code, period="daily", start_date="20260401", end_date=datetime.date.today().strftime("%Y%m%d"))
            if len(df) > 10:
                quotes[code]['ma5'] = round(df['收盘'].rolling(5).mean().iloc[-1], 2)
                quotes[code]['ma10'] = round(df['收盘'].rolling(10).mean().iloc[-1], 2)
        except:
            quotes[code]['ma5'] = None
            quotes[code]['ma10'] = None
except Exception as e:
    print(f"⚠️ 获取均线失败: {e}")

# 保存
with open("/tmp/lobster_quotes.json", "w") as f:
    json.dump(quotes, f, ensure_ascii=False, indent=2)

# 输出当前行情
now_hm = datetime.datetime.now().strftime('%H:%M')
print(f"\n📊 持仓行情 {now_hm}")
print("=" * 50)
for p in positions:
    code = p['code']
    if code in quotes:
        q = quotes[code]
        buy_price = p.get('buy_price')
        pnl = ""
        if buy_price and buy_price > 0:
            pnl = f" 浮盈{((q['price'] - buy_price) / buy_price * 100):+.1f}%"
        ma5_str = f"MA5={q.get('ma5','?')}" if q.get('ma5') else ""
        ma10_str = f"MA10={q.get('ma10','?')}" if q.get('ma10') else ""
        print(f"  {q['name']}({code}): {q['price']} ({q['pct']:+.2f}%){pnl}")
        if ma5_str or ma10_str:
            print(f"    {ma5_str} {ma10_str}")
PYEOF
```

---

## 步骤2.5：日内分时追踪 — 主高/次高记录（用于分时止盈）

```bash
python3 << 'PYEOF'
import json, datetime, os, subprocess, re

TRACK_FILE = "/tmp/lobster_intraday_tracking.json"
today = datetime.date.today().strftime('%Y-%m-%d')

# 读取已有追踪状态
track = {}
if os.path.exists(TRACK_FILE):
    try:
        with open(TRACK_FILE) as f:
            track = json.load(f)
    except:
        track = {}

# 重置为新的一天
if track.get('date') != today:
    track = {'date': today, 'positions': {}}

# 读取当前行情
with open("/tmp/lobster_quotes.json") as f:
    quotes = json.load(f)
with open("/tmp/lobster_positions.json") as f:
    positions = json.load(f)

now_ts = datetime.datetime.now().strftime('%H:%M:%S')

# 获取指数分时（用于非龙头指数参考）
index_codes = ['sz399001', 'sz399006']
try:
    r = subprocess.run(["curl","-s","--max-time","5",f"https://qt.gtimg.cn/q={','.join(index_codes)}"], capture_output=True, timeout=8)
    raw = r.stdout
    for enc in ["gb2312","gbk","utf-8"]:
        try: txt = raw.decode(enc); break
        except: continue
    else: txt = raw.decode("utf-8","replace")
    
    for line in txt.split(";"):
        m = re.search(r'v_(\w+)="([^"]*)"', line)
        if m:
            p = m.group(2).split("~")
            if len(p) > 3:
                idx_code = m.group(1)[2:]
                idx_price = float(p[4]) if p[4] else 0  # p[4]=当前价
                if 'index_tracking' not in track:
                    track['index_tracking'] = {}
                if idx_code not in track['index_tracking']:
                    track['index_tracking'][idx_code] = {'main_high': idx_price, 'main_high_time': now_ts}
                else:
                    if idx_price > track['index_tracking'][idx_code]['main_high']:
                        track['index_tracking'][idx_code]['second_high'] = track['index_tracking'][idx_code]['main_high']
                        track['index_tracking'][idx_code]['main_high'] = idx_price
                        track['index_tracking'][idx_code]['main_high_time'] = now_ts
except:
    pass

for p in positions:
    code = p['code']
    if code not in quotes:
        continue
    cur_price = quotes[code]['price']
    
    if code not in track['positions']:
        track['positions'][code] = {
            'name': p['name'],
            'dimension': p.get('dimension', ''),
            'main_high': cur_price, 'main_high_time': now_ts,
            'second_high': None, 'second_high_time': None,
            'sub_sold': False, 'signal': None
        }
    else:
        pos_track = track['positions'][code]
        prev_main = pos_track['main_high']
        
        if cur_price > prev_main:
            # 创日内新高 → 原主高降为次高
            pos_track['second_high'] = prev_main
            pos_track['second_high_time'] = pos_track['main_high_time']
            pos_track['main_high'] = cur_price
            pos_track['main_high_time'] = now_ts
        elif cur_price < prev_main:
            if pos_track['second_high'] is None or cur_price > pos_track['second_high']:
                pos_track['second_high'] = cur_price
                pos_track['second_high_time'] = now_ts
        
        # 分时止盈信号：次高已经形成且不过主高
        sec_h = pos_track.get('second_high')
        if sec_h and pos_track['signal'] is None:
            diff = (pos_track['main_high'] - sec_h) / sec_h * 100
            if diff > 0.1:
                pos_track['signal'] = "止盈"
                pos_track['signal_reason'] = f"次高{sec_h}不过主高{pos_track['main_high']}(差距{diff:.2f}%)"

with open(TRACK_FILE, 'w') as f:
    json.dump(track, f, ensure_ascii=False, indent=2)

# 输出分时状态
print(f"\n📈 分时追踪 {now_ts}")
print("=" * 50)
for code, pt in track['positions'].items():
    if pt.get('signal'):
        print(f"  🚩 {pt['name']}({code}) — {pt['signal_reason']}")
    elif pt.get('second_high'):
        diff = ((pt['main_high'] - pt['second_high']) / pt['second_high'] * 100)
        arrow = "⬆" if diff > 0.5 else "↗" if diff > 0 else "↘"
        print(f"  {pt['name']}({code}): 主高{pt['main_high']}@{pt['main_high_time']} 次高{pt['second_high']}@{pt['second_high_time']} {arrow}{diff:+.2f}%")
    else:
        print(f"  {pt['name']}({code}): 主高{pt['main_high']}@{pt['main_high_time']}（暂无次高）")

if 'index_tracking' in track:
    for ic, it in track['index_tracking'].items():
        iname = "深证" if ic == '399001' else "创业板"
        sec = it.get('second_high')
        if sec:
            print(f"  📊 {iname}指数: 主高{it['main_high']}@{it['main_high_time']} 次高{sec}")
        else:
            print(f"  📊 {iname}指数: 主高{it['main_high']}@{it['main_high_time']}（暂无次高）")
PYEOF
```

---

## 步骤3：止损/止盈判断 + 告警

```bash
python3 << 'PYEOF'
import json, datetime

# 读取数据
try:
    with open("/tmp/lobster_positions.json") as f:
        positions = json.load(f)
    with open("/tmp/lobster_quotes.json") as f:
        quotes = json.load(f)
except:
    print("⚠️ 数据读取失败")
    exit(1)

# 读取分时追踪（分时止盈用）
try:
    with open("/tmp/lobster_intraday_tracking.json") as f:
        track = json.load(f)
    intra_positions = track.get('positions', {})
except:
    intra_positions = {}

alerts = []

for p in positions:
    code = p['code']
    name = p.get('name', code)
    if code not in quotes:
        continue
    
    q = quotes[code]
    price = q.get('price', 0)
    ma5 = q.get('ma5')
    ma10 = q.get('ma10')
    buy_price = p.get('buy_price')
    dimension = p.get('dimension', '')
    
    # ==========================================
    # 1.0/2.0 止盈 → 分时止盈（）
    # 优先级高于固定%止盈
    # ==========================================
    if '1.0' in dimension or '2.0' in dimension:
        pt = intra_positions.get(code, {})
        if pt.get('signal') == '止盈':
            pnl = ((price - buy_price) / buy_price * 100) if buy_price and buy_price > 0 else 0
            alerts.append({
                "level": "💰", "type": "分时止盈(次高<主高)",
                "stock": f"{name}({code})", "dimension": dimension,
                "pnl_pct": round(pnl, 1), "trigger_price": price,
                "detail": pt.get('signal_reason', '次高不过主高'),
                "action": "卖出全部（龙虾规则：次高不过主高就砸）"
            })
    
    # ==========================================
    # 止损判断（按维度）
    # ==========================================
    if '1.0' in dimension:
        stop_price = buy_price * 0.95 if buy_price and buy_price > 0 else 0
        if stop_price > 0 and price < stop_price:
            alerts.append({
                "level": "🚨", "type": "1.0硬止损-5%",
                "stock": f"{name}({code})", "dimension": dimension,
                "trigger_price": price, "stop_price": round(stop_price, 2),
                "detail": f"现价{price:.2f} < 止损价{stop_price:.2f}(买入-5%)",
                "action": "次日竞价割肉"
            })
    
    elif '2.0' in dimension:
        stop_price = buy_price * 0.93 if buy_price and buy_price > 0 else 0
        if stop_price > 0 and price < stop_price:
            alerts.append({
                "level": "🚨", "type": "2.0硬止损-7%",
                "stock": f"{name}({code})", "dimension": dimension,
                "trigger_price": price, "stop_price": round(stop_price, 2),
                "detail": f"现价{price:.2f} < 止损价{stop_price:.2f}(买入-7%)",
                "action": "次日竞价割肉"
            })
    
    elif '3.0' in dimension:
        if ma5 and ma10 and ma5 < ma10:
            alerts.append({
                "level": "🚨", "type": "3.0技术止损MA5<MA10",
                "stock": f"{name}({code})", "dimension": dimension,
                "trigger_price": price,
                "detail": f"MA5={ma5} < MA10={ma10}，趋势破坏",
                "action": "持有期满后执行"
            })
    
    # ==========================================
    # 3.0 Tier-1退出提示（盘中简单；完整在收盘复盘执行）
    # ==========================================
    if '3.0' in dimension and buy_price and buy_price > 0:
        pnl_pct = (price - buy_price) / buy_price * 100
        if pnl_pct > 10:
            alerts.append({
                "level": "💰", "type": "Tier-1止盈观察",
                "stock": f"{name}({code})", "dimension": dimension,
                "pnl_pct": round(pnl_pct, 1), "trigger_price": price,
                "detail": f"浮盈{pnl_pct:.1f}% > 10%，检查催化兑现/板块分化",
                "action": "收盘复盘时评估Tier-1退出条件"
            })

# 输出告警
now_hm = datetime.datetime.now().strftime('%H:%M')
if alerts:
    print(f"\n🔔 卖点告警 {now_hm}")
    print("=" * 50)
    for a in alerts:
        print(f"{a['level']} {a['stock']} — {a['type']}")
        print(f"    {a['detail']}")
        print(f"    → {a['action']}")
    print("=" * 50)
    with open("/tmp/lobster_sell_alerts.json", "w") as f:
        json.dump({"time": now_hm, "alerts": alerts}, f, ensure_ascii=False, indent=2)
else:
    print(f"\n✅ {now_hm} 暂无止损/止盈触发，持仓正常")
    import os
    try: os.remove("/tmp/lobster_sell_alerts.json")
    except: pass
PYEOF
```

---

## 步骤4：发送告警（如有）

```bash
if [ -f /tmp/lobster_sell_alerts.json ]; then
    python3 << 'PYEOF'
import json
try:
    with open("/tmp/lobster_sell_alerts.json") as f:
        data = json.load(f)
    alerts = data.get('alerts', [])
    if alerts:
        lines = [f"🔔 卖点告警 {data.get('time','')}", ""]
        for a in alerts:
            lines.append(f"{a['level']} {a['stock']} — {a['type']}")
            lines.append(f"   {a['detail']}")
            lines.append(f"   → {a['action']}")
        print("\n".join(lines))
except:
    pass
PYEOF
fi
```

---

## 步骤5：IMA同步（可选）

```bash
if [ -f /tmp/lobster_sell_alerts.json ]; then
    python3 -c "
import json, datetime
with open('/tmp/lobster_sell_alerts.json') as f:
    data = json.load(f)
if data.get('alerts'):
    with open('/tmp/lobster_sellpoint_{}.md'.format(datetime.date.today()), 'w') as f:
        f.write('# 卖点监控 {}\n\n'.format(data.get('time','')))
        for a in data['alerts']:
            f.write('## {} {} — {}\n'.format(a['level'], a['stock'], a['type']))
            f.write('- {}\n'.format(a['detail']))
            f.write('- {}\n\n'.format(a['action']))
    print('✅ 告警已写入临时文件')
"
fi
```

---

## 监控频率

| 时间段 | 频率 | 说明 |
|--------|------|------|
| 9:30-11:30 | 每30分钟 | 早盘监控 |
| 13:00-14:30 | 每30分钟 | 午盘监控 |
| 14:50 | 单次 | 尾盘预警（收盘前提醒） |

---

## 触发条件汇总（v3）

| 维度 | 逻辑 | 条件 | 级别 | 执行 |
|------|------|------|------|------|
| **1.0/2.0止盈** | 分时止盈 | 次高 < 主高（涨不动了） | 💰 | 卖出全部 |
| **1.0止损** | 硬止损 | 现价 < 买入价×0.95（-5%） | 🚨 | 次日竞价割肉 |
| **2.0止损** | 硬止损 | 现价 < 买入价×0.93（-7%） | 🚨 | 次日竞价割肉 |
| **3.0止损** | 技术止损 | MA5 < MA10 | 🚨 | 持有期满执行 |
| **3.0止盈** | Tier-1退出 | 浮盈>10%+催化兑现/板块分化 | 💰 | 收盘复盘评估 |

---

**版本**：v3（分时止盈+Tier-1退出+维度止损对齐规则+模拟持仓.json读取+自动卖出）
**更新**：2026-05-20 15:15

---

## 步骤6：模拟卖出 + 情绪强制减仓

步骤3检测到止损/止盈信号后，调用 `simulated_trading.sell()` 自动执行卖出。
另外根据涨跌家数判断是否需要情绪强制减仓/清仓：

```bash
python3 << 'PYEOF'
import sys, json, re
sys.path.insert(0, "/Users/yuefengshen/.qclaw/workspace-1gwpiwf3hr163jz5/scripts")
from simulated_trading import sell, emotion_force_sell, get_emotion_rule

# Part 1: 止损/止盈卖出
try:
    with open("/tmp/lobster_sell_alerts.json") as f:
        data = json.load(f)
    alerts = data.get('alerts', [])
    
    if not alerts:
        print("无卖点告警，无需卖出")
    else:
        try:
            with open("/tmp/lobster_quotes.json") as f:
                quotes = json.load(f)
        except:
            quotes = {}
        
        for a in alerts:
            m = re.search(r'\((\d{6})\)', a['stock'])
            if not m: continue
            code = m.group(1)
            price = a.get('trigger_price', 0)
            if code in quotes: price = quotes[code]['price']
            if price <= 0: continue
            result = sell(code, price, a['detail'], a['type'])
            print(f"  {a['level']} {result}")
except Exception as e:
    print(f"⚠️ 止损卖出异常: {e}")

# Part 2: 情绪强制减仓/清仓
try:
    with open("/tmp/lobster_buypoint_data.json") as f:
        bp = json.load(f)
    up_count = bp.get('up_count', 0)
    key, rule = get_emotion_rule(up_count)
    
    if key in ['extreme_hot', 'ice_point']:
        with open("/tmp/lobster_quotes.json") as f:
            quotes = json.load(f)
        price_map = {c: q['price'] for c, q in quotes.items()}
        # 补充持仓股价格
        from simulated_trading import _load
        pos_data = _load()
        for p in pos_data['positions']:
            if p['code'] not in price_map:
                q_prefix = 'sh' if p['code'].startswith('6') else 'sz'
                import subprocess
                r = subprocess.run(['curl','-s','--max-time','10',f'https://qt.gtimg.cn/q={q_prefix}{p["code"]}'], capture_output=True, timeout=12)
                for enc in ['gb2312','gbk','utf-8']:
                    try: t=r.stdout.decode(enc); break
                    except: continue
                pp = t.split('~')
                if len(pp)>3 and pp[4]: price_map[p['code']] = float(pp[4])  # pp[4]=当前价
        
        results = emotion_force_sell(None, up_count, price_map)
        if results:
            for r in results: print(r)
        else:
            print(f"情绪极端({key})但无需减仓（仓位已在限额内）")
    else:
        print(f"情绪正常({key}, 涨跌{up_count})，无需强制减仓")
except Exception as e:
    print(f"⚠️ 情绪减仓检查异常: {e}")
PYEOF
```
