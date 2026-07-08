# 龙虾尾盘专项 — cron 任务指令（v1）

> **频率**：每日 14:45（工作日）
> **超时**：120秒
> **核心**：尾盘10分钟全维度检查 — 情绪定调、持仓决策、最后操作窗口

---

## 步骤1：交易日判断

```bash
python3 -c "
import datetime, sys
HOLIDAYS = {'2026-01-01','2026-01-02','2026-01-03','2026-01-26','2026-01-27','2026-01-28','2026-01-29','2026-01-30','2026-01-31','2026-02-01','2026-02-02','2026-02-03','2026-02-04','2026-04-04','2026-04-05','2026-04-06','2026-05-01','2026-05-02','2026-05-03','2026-05-04','2026-05-05','2026-06-19','2026-06-20','2026-06-21','2026-09-25','2026-09-26','2026-09-27','2026-10-01','2026-10-02','2026-10-03','2026-10-04','2026-10-05','2026-10-06','2026-10-07'}
WORKDAYS = {'2026-01-25','2026-02-08','2026-04-26','2026-09-28','2026-10-10'}
d = datetime.date.today()
s = d.isoformat()
if s in HOLIDAYS or (d.weekday() >= 5 and s not in WORKDAYS):
    print('⚠️ 非交易日，跳过尾盘专项')
    sys.exit(0)
else:
    print(f'✅ 交易日 {s}，执行尾盘专项')
"
```

## 步骤2：尾盘情绪定调

```bash
python3 << 'PYEOF'
import subprocess, re, datetime

print("=== 尾盘情绪定调 ===")

# 获取涨跌家数
r = subprocess.run(['curl','-sL','--max-time','15','-A','Mozilla/5.0',
    'https://legulegu.com/stockdata/market-activity'],
    capture_output=True, text=True, timeout=18)

up, down = 0, 0
m = re.search(r'上涨:(\d+)\s+下跌:(\d+)', r.text)
if m:
    up, down = int(m.group(1)), int(m.group(2))
    total = up + down
else:
    print("⚠️ 涨跌家数获取失败，使用上次缓存")

emotion = up
if emotion < 1500:
    phase = "冰点"
    dim_main = "1.0"
    pos_limit = "5成"
elif emotion < 2000:
    phase = "弱势"
    dim_main = "1.0(3.0熔断)"
    pos_limit = "5成"
elif emotion < 2500:
    phase = "温和"
    dim_main = "1.0+3.0"
    pos_limit = "9成"
elif emotion < 3500:
    phase = "活跃"
    dim_main = "2.0+1.0"
    pos_limit = "5-7成"
else:
    phase = "极度高潮"
    dim_main = "辅助模式"
    pos_limit = "2成"

print(f"  涨:{up} 跌:{down} → {phase}({emotion})")
print(f"  主导维度: {dim_main} | 仓位上限: {pos_limit}")

# 获取指数
r2 = subprocess.run(['curl','-s','--max-time','10',
    'https://qt.gtimg.cn/q=sh000001,sz399001,sz399006'],
    capture_output=True, timeout=12)
for enc in ['gb2312','gbk','utf-8']:
    try: txt = r2.stdout.decode(enc); break
    except: continue
else: txt = r2.stdout.decode('utf-8','replace')

for line in txt.split(';'):
    m2 = re.search(r'v_(\w+)="([^"]*)"', line)
    if m2:
        p = m2.group(2).split('~')
        if len(p) > 34:
            name = p[1]
            price = float(p[4]) if p[4] else 0
            pct = float(p[32]) if p[32] else 0
            print(f"  {name}: {price:.2f} ({pct:+.2f}%)")

# 保存情绪数据供后续用
import json
emotion_data = {'up': up, 'down': down, 'emotion': emotion, 'phase': phase, 
                'dim_main': dim_main, 'pos_limit': pos_limit, 'time': '14:45'}
with open('/tmp/lobster_buypoint_data.json', 'w') as f:
    json.dump(emotion_data, f, ensure_ascii=False, indent=2)

PYEOF
```

## 步骤3：持仓尾盘评估

```bash
python3 << 'PYEOF'
import json, subprocess, re, datetime, sys
from pathlib import Path

BASE = Path("/Users/yuefengshen/.qclaw/workspace-1gwpiwf3hr163jz5")
print("\n=== 持仓尾盘评估 ===")

try:
    with open(BASE / "trading/模拟持仓.json") as f:
        data = json.load(f)
except:
    print("⚠️ 模拟持仓不存在，跳过")
    sys.exit(0)

positions = data.get('positions', [])
if not positions:
    print("📋 无持仓")
    sys.exit(0)

# 获取实时行情
codes = [p['code'] for p in positions]
q_list = [f"sh{c}" if c.startswith('6') else f"sz{c}" for c in codes]
q_str = ",".join(q_list)

r = subprocess.run(["curl","-s","--max-time","10",f"https://qt.gtimg.cn/q={q_str}"],
    capture_output=True, timeout=12)
for enc in ["gb2312","gbk","utf-8"]:
    try: txt = r.stdout.decode(enc); break
    except: continue
else: txt = r.stdout.decode("utf-8","replace")

quotes = {}
for line in txt.split(";"):
    m = re.search(r'v_(\w+)="([^"]*)"', line)
    if m:
        p = m.group(2).split("~")
        if len(p) > 37:
            code = p[2]
            quotes[code] = {
                "name": p[1], "price": float(p[4]) if p[4] else 0,
                "pct": float(p[32]) if p[32] else 0,
                "high": float(p[33]) if p[33] else 0,
                "low": float(p[34]) if p[34] else 0,
            }

alerts = []

for pos in positions:
    code = pos['code']
    q = quotes.get(code, {})
    cur_price = q.get('price', 0)
    buy_price = float(pos['buy_price'])
    cost = float(pos.get('cost', buy_price * int(pos['shares'])))
    dim = pos.get('dimension', '')
    can_sell = pos.get('can_sell', False)
    
    if cur_price == 0:
        print(f"  ⚠️ {pos['name']}({code}) 行情获取失败")
        continue
    
    pnl_pct = (cur_price - buy_price) / buy_price * 100
    pnl = (cur_price - buy_price) * int(pos['shares'])
    is_zt = q.get('pct', 0) >= 9.9  # 涨停判断
    
    # 尾盘专项检查
    tags = []
    
    # 1. 超短卖点：涨停次日14:50未封板 → 卖出
    if dim in ['1.0一进二', '1.0分歧低吸'] and can_sell:
        if not is_zt and q.get('pct', 0) < 7:
            tags.append("⚠️超短：涨停次日未封板")
            alerts.append({'code': code, 'name': pos['name'], 'action': 'SELL', 
                          'reason': '超短卖点-涨停次日未封板', 'dimension': dim})
    
    # 2. 硬止损检查
    if dim.startswith('1.0') and pnl_pct <= -5:
        tags.append("🔴1.0止损-5%")
        alerts.append({'code': code, 'name': pos['name'], 'action': 'SELL',
                      'reason': f'1.0硬止损{pnl_pct:.1f}%', 'dimension': dim})
    elif dim.startswith('2.0') and pnl_pct <= -7:
        tags.append("🔴2.0止损-7%")
        alerts.append({'code': code, 'name': pos['name'], 'action': 'SELL',
                      'reason': f'2.0硬止损{pnl_pct:.1f}%', 'dimension': dim})
    
    # 3. 3.0技术止损：MA5<MA10（简化判断，需akshare）
    if dim.startswith('3.0'):
        try:
            import akshare as ak
            df = ak.stock_zh_a_hist(symbol=code, period="daily", start_date="20260401",
                                   end_date=datetime.date.today().strftime("%Y%m%d"))
            if len(df) > 10:
                ma5 = df['收盘'].rolling(5).mean().iloc[-1]
                ma10 = df['收盘'].rolling(10).mean().iloc[-1]
                if ma5 < ma10:
                    tags.append("🔴3.0技术止损(MA5<MA10)")
                    alerts.append({'code': code, 'name': pos['name'], 'action': 'SELL',
                                  'reason': '3.0技术止损MA5<MA10', 'dimension': dim})
        except:
            pass
    
    # 4. 分时止盈检查（尾盘版：日内次高低于主高）
    if dim in ['1.0一进二', '1.0分歧低吸', '2.0板块卡位'] and can_sell and pnl_pct > 3:
        high = q.get('high', 0)
        if high > 0 and cur_price < high * 0.97:
            tags.append(f"💰分时回落(高{high}→现{cur_price})")
    
    # 5. T+1标记
    if not can_sell:
        tags.append("🔒T+1")
    
    emoji = "🟢" if pnl >= 0 else "🔴"
    zt_tag = " 🔥涨停" if is_zt else ""
    print(f"  {emoji} {pos['name']}({code}) [{dim}] {cur_price} ({pnl_pct:+.2f}%){zt_tag}")
    if tags:
        print(f"     {' | '.join(tags)}")

# 保存告警
if alerts:
    with open('/tmp/lobster_sell_alerts.json', 'w') as f:
        json.dump(alerts, f, ensure_ascii=False, indent=2)
    print(f"\n  ⚠️ {len(alerts)}条卖点告警")
else:
    import os
    if os.path.exists('/tmp/lobster_sell_alerts.json'):
        os.remove('/tmp/lobster_sell_alerts.json')
    print(f"\n  ✅ 无卖点告警")

PYEOF
```

## 步骤4：自动执行卖出（如有告警）

```bash
python3 << 'PYEOF'
import json, sys, os

BASE = "/Users/yuefengshen/.qclaw/workspace-1gwpiwf3hr163jz5"

alert_path = "/tmp/lobster_sell_alerts.json"
if not os.path.exists(alert_path):
    print("✅ 无告警，无需执行卖出")
    sys.exit(0)

with open(alert_path) as f:
    alerts = json.load(f)

if not alerts:
    print("✅ 无告警")
    sys.exit(0)

sys.path.insert(0, f"{BASE}/scripts")
from simulated_trading import sell

print("=== 执行尾盘自动卖出 ===")
for a in alerts:
    try:
        result = sell(a['code'], reason=a['reason'])
        print(f"  ✅ {a['name']}({a['code']}) 卖出成功: {result}")
    except Exception as e:
        print(f"  ❌ {a['name']}({a['code']}) 卖出失败: {e}")

PYEOF
```

## 步骤5：尾盘异动扫描（板块+涨停）

```bash
python3 << 'PYEOF'
import subprocess, re

print("\n=== 尾盘异动扫描 ===")

# 涨停池快查
try:
    import akshare as ak
    import datetime
    today = datetime.date.today().strftime("%Y%m%d")
    df = ak.stock_zt_pool_em(date=today)
    if len(df) > 0:
        # 按板块统计
        from collections import Counter
        sectors = Counter(df.get('所属行业', df.get('板块', [])))
        top3 = sectors.most_common(3)
        print(f"  今日涨停: {len(df)}只")
        for s, c in top3:
            print(f"  🔥 {s}: {c}只涨停")
    else:
        print("  今日无涨停")
except Exception as e:
    print(f"  ⚠️ 涨停池获取失败: {e}")

PYEOF
```

## 步骤6：情绪强制减仓检查

```bash
python3 << 'PYEOF'
import json

print("\n=== 情绪强制减仓检查 ===")

try:
    with open('/tmp/lobster_buypoint_data.json') as f:
        em = json.load(f)
except:
    print("⚠️ 无情绪数据")
    import sys; sys.exit(0)

emotion = em.get('emotion', 0)
if emotion < 1500:
    print(f"  🚨 冰点({emotion}) → 建议清仓非1.0持仓")
elif emotion < 2000:
    print(f"  ⚠️ 弱势({emotion}) → 3.0熔断，1.0仓位5成上限")
elif emotion > 3500:
    print(f"  🔴 极度高潮({emotion}) → 辅助模式，仓位上限2成")
else:
    print(f"  ✅ 情绪正常({emotion})，无需强制减仓")

PYEOF
```

## 步骤7：输出尾盘汇总

```bash
python3 << 'PYEOF'
import json, os, datetime

print("\n=== 尾盘汇总 ===")
print(f"时间: 14:45 | 日期: {datetime.date.today()}")

# 读取情绪
try:
    with open('/tmp/lobster_buypoint_data.json') as f:
        em = json.load(f)
    print(f"情绪: {em.get('up',0)}涨/{em.get('down',0)}跌 → {em.get('phase','?')} | 主导: {em.get('dim_main','?')} | 仓位上限: {em.get('pos_limit','?')}")
except:
    pass

# 读取告警
if os.path.exists('/tmp/lobster_sell_alerts.json'):
    with open('/tmp/lobster_sell_alerts.json') as f:
        alerts = json.load(f)
    print(f"卖点告警: {len(alerts)}条（已自动执行）")
else:
    print("卖点告警: 无")

print("尾盘专项完成 ✅")
PYEOF
```

## IMA同步

```bash
bash /Users/yuefengshen/.qclaw/workspace-1gwpiwf3hr163jz5/scripts/ima_sync.sh /tmp/lobster_sellpoint_$(date +%Y%m%d).md "龙虾尾盘专项 $(date +%Y-%m-%d)" 2>>/tmp/ima-errors.log || echo "IMA同步跳过(查看: tail /tmp/ima-errors.log)"
```

---

**版本**：v1.0
**更新**：2026-05-23

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
