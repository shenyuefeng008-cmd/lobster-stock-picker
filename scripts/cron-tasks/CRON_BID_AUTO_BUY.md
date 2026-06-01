# 龙虾竞价自动买入 — cron 任务指令（v1）

> **频率**：每个交易日 09:26（竞价结束后立即执行）
> **前置条件**：lobster_bid_filter_v2.py 必须在09:25执行完毕
> **超时**：120秒（09:26-09:28 竞价撮合期，给足时间）
**注意**：CRON任务级别需同步设置120秒timeout，否则Python脚本跑完但CRON已超时
> **核心**：竞价过滤结果 → 立即自动买入 → 简短输出

---

## 步骤1：读取竞价过滤结果

```bash
python3 << 'PYEOF'
import json, subprocess, re, datetime, sys
sys.path.insert(0, "/Users/yuefengshen/.qclaw/workspace-1gwpiwf3hr163jz5/scripts")
from simulated_trading import buy, check_position_limit, _load

today = datetime.date.today().strftime('%Y-%m-%d')
now_hm = datetime.datetime.now().strftime('%H:%M')

# 每日盘前解锁T+1
from simulated_trading import unlock_t1
unlocked = unlock_t1()
if unlocked:
    print(f"🔓 T+1解锁: {unlocked}只持仓")

print(f"{'='*40}")
print(f"⚡ 竞价自动买入 {now_hm}")
print(f"{'='*40}")

# 读取竞价过滤结果
try:
    with open('/tmp/lobster_bid_result.json') as f:
        bid = json.load(f)
    if bid.get('date') != today:
        print("⚠️ 竞价结果日期非今天，跳过")
        sys.exit(0)
except Exception as e:
    print(f"⚠️ 无法读取竞价结果: {e}")
    sys.exit(0)

# 读取涨跌家数
try:
    r2 = subprocess.run(["curl","-s","-L","--max-time","10","-A","Mozilla/5.0","https://legulegu.com/stockdata/market-activity"], capture_output=True, text=True, timeout=12)
    mu = re.search(r'(\d+)家上涨', r2.stdout)
    up = int(mu.group(1)) if mu else 0
except:
    up = 0

print(f"情绪: 涨跌家数 {up}")
print(f"主导维度: {bid['emotion'].get('主导维度', '1.0')}")
print(f"仓位上限: {bid['emotion'].get('总仓位上限', 5)}成")

# 读取当前持仓状态
data = _load()
current_pct = sum(p['cost'] for p in data['positions']) / data['_meta'].get('initial_capital', 1000000) * 100
print(f"当前仓位: {current_pct:.1f}%")

# 仓位上限
max_pos = bid['emotion'].get('总仓位上限', 5)
remaining_pct = max(0, max_pos - current_pct)
if remaining_pct < 5:
    print(f"⚠️ 仓位不足（剩余{rounding(remaining_pct)}%），跳过自动买入")
else:
    print(f"可买入仓位: {remaining_pct:.1f}%")

print()
PYEOF
```

## 步骤2：竞价过滤通过 → 立即买入

> 竞价低开/下杀 + 竞量充足 → 视为分歧低吸买点，立即买入

```bash
python3 << 'PYEOF'
import json, subprocess, re, datetime, sys
sys.path.insert(0, "/Users/yuefengshen/.qclaw/workspace-1gwpiwf3hr163jz5/scripts")
from simulated_trading import buy, check_position_limit, _load

today = datetime.date.today().strftime('%Y-%m-%d')

# 读取涨跌家数
try:
    r2 = subprocess.run(["curl","-s","-L","--max-time","10","-A","Mozilla/5.0","https://legulegu.com/stockdata/market-activity"], capture_output=True, text=True, timeout=12)
    mu = re.search(r'(\d+)家上涨', r2.stdout)
    up_count = int(mu.group(1)) if mu else 0
except:
    up_count = 0

# 读取竞价结果
with open('/tmp/lobster_bid_result.json') as f:
    bid = json.load(f)

# 检查仓位
data = _load()
max_pos = bid['emotion'].get('总仓位上限', 5)
current_pct = sum(p['cost'] for p in data['positions']) / data['_meta'].get('initial_capital', 1000000) * 100
if current_pct >= max_pos:
    print("⚠️ 仓位已满，跳过自动买入")
    sys.exit(0)

# 仓位检查（按维度分配）
# 1.0一进二/分歧低吸：单只10%仓位
# 2.0板块卡位：单只10%仓位
# 优先买1.0，其次2.0

results = []
for dim_key, dimension, pos_pct in [
    ('1.0分歧低吸', '1.0分歧低吸', 10),
    ('1.0一进二', '1.0一进二', 10),
    ('2.0板块卡位', '2.0板块卡位', 10),
    ('3.0趋势低吸', '3.0趋势低吸', 15),
]:
    item = bid['results'].get(dim_key)
    if not item:
        continue
    
    code = item['code']
    name = item['name']
    change_pct = item['change_pct']
    volume = item.get('volume', 0)
    
    # 3.0维度：检查locked状态
    if '3.0' in dim_key:
        # 从watchlist候选中查找locked状态
        try:
            with open('/tmp/lobster_watchlist_candidates.json') as wf:
                wl = json.load(wf)
            wl_items = wl.get('candidates', {}).get('3.0趋势低吸', [])
            wl_stock = next((s for s in wl_items if s.get('代码') == code), {})
            is_locked = wl_stock.get('locked', False)
            lock_reason = wl_stock.get('locked_reason') or wl_stock.get('锁定原因', '')
        except:
            is_locked, lock_reason = True, '候选数据缺失'
        
        if is_locked:
            print(f"🔒 {name}({code}) 3.0已锁定（{lock_reason}），跳过买入")
            continue
        
        # 3.0额外验证：开盘后实时情绪必须>=2000
        if up_count < 2000:
            print(f"🔒 {name}({code}) 实时情绪{up_count}<2000，3.0熔断，跳过买入")
            continue
        print(f"✅ {name}({code}) 3.0已解锁，情绪{up_count}≥2000，允许买入")
    
    # 检查是否已在持仓
    data = _load()
    if any(p['code'] == code for p in data['positions']):
        print(f"⏭️ {name}({code}) 已在持仓，跳过")
        continue
    
    # 检查仓位
    data = _load()
    current_pct = sum(p['cost'] for p in data['positions']) / data['_meta'].get('initial_capital', 1000000) * 100
    allowed, allowed_pct, msg = check_position_limit(data, up_count, dimension)
    
    if not allowed:
        print(f"⚠️ {name}({code}) 仓位不足: {msg}")
        continue
    
    # 获取实时价格（开盘后用现价）
    q = f"sh{code}" if code.startswith("6") else f"sz{code}"
    r = subprocess.run(["curl","-s","--max-time","10",f"https://qt.gtimg.cn/q={q}"], capture_output=True, timeout=12)
    for enc in ["gb2312","gbk","utf-8"]:
        try: txt = r.stdout.decode(enc); break
        except: continue
    else: txt = r.stdout.decode("utf-8","replace")
    pp = txt.split("~")
    if len(pp) < 4:
        print(f"⚠️ {name}({code}) 无法获取价格")
        continue
    price = float(pp[3])  # pp[3]=现价
    
    # 买入原因
    if dim_key == '1.0分歧低吸':
        reason = f"竞价低开{change_pct:+.2f}%，竞量{volume}手，分歧低吸买点"
    elif dim_key == '1.0一进二':
        reason = f"竞价高开{change_pct:+.2f}%，竞量{volume}手，一进二买点"
    else:
        reason = f"竞价{change_pct:+.2f}%，竞量{volume}手，板块卡位买点"
    
    # 自动买入
    result = buy(code, name, price, reason, dimension, up_count, pos_pct)
    results.append(f"✅ 竞价买入 | {result}")
    
    # 每买一只重新检查仓位
    data = _load()
    current_pct = sum(p['cost'] for p in data['positions']) / data['_meta'].get('initial_capital', 1000000) * 100
    if current_pct >= max_pos:
        print(f"\n⚠️ 仓位已满（{current_pct:.1f}%），停止买入")
        break

# 输出结果
print()
if results:
    print(f"📋 竞价自动买入结果 ({len(results)}只):")
    for r in results:
        print(f"  {r}")
    print()
    from simulated_trading import status
    print(status())
else:
    print("📋 竞价无符合条件的标的，跳过自动买入")

# 保存通知
if results:
    notify_path = f"/tmp/lobster_buy_notification_{today.replace('-','')}.txt"
    with open(notify_path, 'w') as f:
        f.write("⚡ 竞价自动买入:\n")
        for r in results:
            f.write(r + "\n")
    print(f"\n✅ 通知已保存: {notify_path}")
PYEOF
```

## 步骤3：立即推送竞价结果（优先！用户09:33前要看到）

> ⚡ 这一步必须在步骤2完成后**立即执行**，不等IMA同步和记忆写入

将步骤2的输出结果（竞价买入结果 + 持仓状态）作为消息**立即推送**给用户。
关键信息：
- 通过了哪些维度、买了什么、价格、仓位
- 当前情绪和仓位上限
- 如果没有符合条件的，也要告知

## 步骤4：同步IMA知识库（后台执行）

```bash
bash /Users/yuefengshen/.qclaw/workspace-1gwpiwf3hr163jz5/scripts/ima_sync.sh 竞价自动买入 2>>/tmp/ima-errors.log
```

---

**版本**：v2（2026-05-26）
**更新**：拆分推送和记忆写入，推送优先（步骤3），IMA同步放后台（步骤4）


## 最后步骤：回复用户（必须执行）

> **关键**：你已执行完所有步骤，生成了任务输出
> **必须**：立即回复用户，将结果完整发送给用户
> **禁止**：NO_REPLY、不回复、只写文件不推送
>
> 回复格式：
> ```
> [任务对应的输出内容]
> ```
