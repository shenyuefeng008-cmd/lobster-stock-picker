# 龙虾竞价全流程 — cron 任务指令（v1 合并版）

> **合并自**：CRON_BID_RECOVERY_TASK.md + CRON_BID_TASK.md + CRON_BID_AUTO_BUY.md
> **合并日期**：2026-06-30
> **执行时间**：交易日 09:20
> **核心任务**：兜底检查(09:20) → 竞价选股(09:25) → 自动买入(09:26-09:28)
> **超时**：180秒（覆盖全流程）

**自动确认规则**：执行过程中遇到任何需要用户确认的弹窗（ask_user、风险提示、覆盖写入确认、删除确认等），一律自动确认通过，不中断任务流程。

## 📎 任务反馈链 — 读取上游建议

**执行任务前，必须先读取 `trading/task-feedback-chain.md` 文件**，查找当日最新的上游任务结论和"给下个任务"建议。
将上游建议融入你的执行决策，但不要盲目照搬——结合当前实际情况判断。

- 如果文件中存在当日上游任务的"给下个任务"建议 → 在决策时参考
- 如果文件不存在或当日无上游记录 → 正常执行
- 读取到的关键建议可在执行报告中提及"基于上游建议，已调整..."

---

## 阶段一：兜底检查（09:20）

> 检查 `/tmp/lobster_premarket_candidates.json` 是否存在，若07:00盘前任务未成功写入则立即补救。

用exec执行：`ls -la /tmp/lobster_premarket_candidates.json 2>/dev/null && echo EXISTS || echo MISSING`

- 如果输出 `EXISTS` → **文件已存在，跳过补救**，直接进入阶段二
- 如果输出 `MISSING` → 继续执行以下补救步骤

### 补救步骤A：重新运行盘前选股引擎

用exec执行：

```
python3 /Users/yuefengshen/.qclaw/workspace-1gwpiwf3hr163jz5/scripts/lobster_premarket_engine.py 2>&1
```

**必须确认**：命令执行完成后，`/tmp/lobster_premarket_candidates.json` 已存在。

### 补救步骤B：读取并汇报结果

用exec执行 `cat /tmp/lobster_premarket_candidates.json`，然后发送告警消息：

```
⚠️ 【盘前选股补救 09:20】
07:00盘前任务未成功，已自动补救。
候选池文件已重新生成，今日候选股如下：

[候选池内容]
```

---

## 阶段二：竞价选股（09:25）

### 步骤2.1：构造竞价输入 + 读取盘前候选池

```python
import json, subprocess

# 读取盘前候选池
with open('/tmp/lobster_premarket_candidates.json') as f:
    data = json.load(f)

# 获取所有候选股代码
codes = []
for tier in data['candidates'].values():
    for stock in tier:
        code = stock['代码']
        codes.append(('sh' + code) if code.startswith('6') else ('sz' + code))

# 获取竞价数据
q_str = ','.join(codes)
cmd = f"curl -s 'https://qt.gtimg.cn/q={q_str}' | iconv -f gbk -t utf-8"
result = subprocess.run(["bash", "-c", cmd], capture_output=True, text=True, timeout=15)

# 写入输入文件
output = {
    'date': data['date'],
    'emotion': data['emotion'],
    'candidates': data['candidates'],
    'bidding_raw': result.stdout
}
with open('/tmp/lobster_bid_input.json', 'w') as f:
    json.dump(output, f, ensure_ascii=False, indent=2)

print("✅ 输入文件已写入 /tmp/lobster_bid_input.json")
```

### 步骤2.2：运行Python竞价过滤脚本

```bash
python3 /Users/yuefengshen/.qclaw/workspace-1gwpiwf3hr163jz5/scripts/lobster_bid_filter_v2.py
```

### 步骤2.2.5：持久化竞价结果（P0-2修复）

> 将竞价结果持久化到 `trading/candidates/` 目录，消除 /tmp 单点故障。

```bash
python3 -c "
import datetime, os, shutil
today = datetime.date.today().strftime('%Y-%m-%d')
src = '/tmp/lobster_bid_result.json'
dst_dir = '/Users/yuefengshen/.qclaw/workspace-1gwpiwf3hr163jz5/trading/candidates'
os.makedirs(dst_dir, exist_ok=True)
dst = f'{dst_dir}/bid_result_{today}.json'
shutil.copy2(src, dst)
print(f'✅ 竞价结果已持久化: {dst}')
"
```

### 步骤2.3：更新关注股.md

```python
import json, datetime

with open('/tmp/lobster_bid_result.json') as f:
    result = json.load(f)

today = datetime.date.today().strftime('%Y-%m-%d')
content = f"""# 🎯 关注股（{today} 竞价更新）

"""

for tier_name, best in result['results'].items():
    if best:
        content += f"""## {tier_name}
- {best['name']}({best['code']}) — 竞价高开{best['change_pct']}%，竞量{best['volume']}手
  - 买入条件：若回踩5日线不破 → 低吸

"""
    else:
        content += f"""## {tier_name}
- ⚠️ 无符合规则标的

"""

content += f"""---
**更新时间**：{datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}
**总仓位上限**：{result['emotion']['总仓位上限']}%
"""

with open('/Users/yuefengshen/.qclaw/workspace-1gwpiwf3hr163jz5/trading/关注股.md', 'w') as f:
    f.write(content)

print("✅ 关注股.md已更新")
```

### 步骤2.4：发送竞价选股消息

```python
import json, subprocess

with open('/tmp/lobster_bid_result.json') as f:
    result = json.load(f)

msg = f"✅ 龙虾竞价选股 {result['date']}\n"
msg += f"情绪：{result['emotion']['涨跌家数']}（{result['emotion']['主导维度']}）\n\n"

for tier, best in result['results'].items():
    msg += f"【{tier}】\n"
    if best:
        msg += f"最优：{best['name']}({best['code']})\n"
        msg += f"- 竞价：高开{best['change_pct']}%，竞量{best['volume']}手\n"
    else:
        msg += "⚠️ 无符合规则标的\n"

subprocess.run([
    'message',
    '--action', 'send',
    '--channel', 'yuanbao',
    '--to', 'direct:Y4oPshFZbMiblavrV+kZZdcSD5YFmAiKomnSLvNDINcwVFC1HLHzx5qq7AG0zjPq',
    '--message', msg
])
```

### 步骤2.5：写入临时复盘文件（供午间复盘读取）

```python
import json, datetime

with open('/tmp/lobster_bid_result.json') as f:
    result = json.load(f)

output = f"""# 龙虾竞价选股 {result['date']}

## 情绪判断
- 涨跌家数：{result['emotion']['涨跌家数']}
- 主导维度：{result['emotion']['主导维度']}
- 总仓位上限：{result['emotion']['总仓位上限']}%

## 选股结果
"""

for tier, best in result['results'].items():
    if best:
        output += f"- {tier}：{best['name']}({best['code']})，高开{best['change_pct']}%，竞量{best['volume']}手\n"
    else:
        output += f"- {tier}：无符合规则标的\n"

with open(f'/tmp/lobster_bid_{result["date"]}.md', 'w') as f:
    f.write(output)

print(f"✅ 复盘文件已写入 /tmp/lobster_bid_{result['date']}.md")
```

---

## 阶段三：自动买入（09:26-09:28）

> **前置条件**：阶段二竞价过滤已执行完毕
> **超时**：120秒（09:26-09:28 竞价撮合期）

### 步骤3.1：读取竞价结果 + 仓位检查

```bash
python3 << 'PYEOF'
import json, subprocess, re, datetime, sys
sys.path.insert(0, "/Users/yuefengshen/.qclaw/workspace-1gwpiwf3hr163jz5/scripts")
from simulated_trading import buy, check_position_limit, _load, unlock_t1

today = datetime.date.today().strftime('%Y-%m-%d')
now_hm = datetime.datetime.now().strftime('%H:%M')

# 每日盘前解锁T+1
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
print(f"仓位上限: {bid['emotion'].get('总仓位上限', 30)}%")

# 读取当前持仓状态
data = _load()
current_pct = sum(p['cost'] for p in data['positions']) / data['_meta'].get('initial_capital', 1000000) * 100
print(f"当前仓位: {current_pct:.1f}%")

# 仓位上限判断
max_pos = bid['emotion'].get('总仓位上限', 5)
remaining_pct = max(0, max_pos - current_pct)
if remaining_pct < 5:
    print(f"⚠️ 仓位不足（剩余{remaining_pct}%），跳过自动买入")
else:
    print(f"可买入仓位: {remaining_pct:.1f}%")

print()
PYEOF
```

### 步骤3.2：逐档位执行买入

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
    
    # 获取实时价格
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
    price = float(pp[3])
    
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

### 步骤3.3：立即推送竞价结果

> 推送买入结果给用户，确保09:33前可见。

---

## 附加：竞价过滤脚本（持久化于 scripts/ 目录）

竞价过滤脚本已固化为 `scripts/lobster_bid_filter_v2.py`，步骤2.2直接调用。如意外丢失，按以下代码重建：

```python
#!/usr/bin/env python3
import json, re

# 读取输入
with open('/tmp/lobster_bid_input.json') as f:
    data = json.load(f)

# 解析竞价数据
bidding_data = {}
for line in data['bidding_raw'].split(';'):
    line = line.strip()
    if not line:
        continue
    m = re.search(r'v_(\w+)="([^"]*)"', line)
    if m:
        code = m.group(1)
        parts = m.group(2).split('~')
        if len(parts) > 36:
            try:
                bidding_data[code] = {
                    'name': parts[1],
                    'change_pct': float(parts[32]) if parts[32] else 0,
                    'volume': int(parts[36]) if parts[36] else 0
                }
            except:
                pass

# 逐档位过滤
results = {}
for tier_name, candidates in data['candidates'].items():
    qualified = []
    for stock in candidates:
        code_key = ('sh' + stock['代码']) if stock['代码'].startswith('6') else ('sz' + stock['代码'])
        if code_key not in bidding_data:
            continue
        bd = bidding_data[code_key]
        change_pct = bd['change_pct']
        volume = bd['volume']
        
        # 过滤条件
        if tier_name == '1.0一进二' and 6 <= change_pct <= 10 and volume >= 150000:
            qualified.append({'name': bd['name'], 'code': stock['代码'], 'change_pct': change_pct, 'volume': volume})
        elif tier_name == '1.0分歧低吸' and -3 <= change_pct <= 0:
            qualified.append({'name': bd['name'], 'code': stock['代码'], 'change_pct': change_pct, 'volume': volume})
        elif tier_name == '2.0板块卡位' and change_pct > 5 and volume >= 100000:
            qualified.append({'name': bd['name'], 'code': stock['代码'], 'change_pct': change_pct, 'volume': volume})
        elif tier_name == '3.0趋势低吸' and -2 <= change_pct <= 3:
            qualified.append({'name': bd['name'], 'code': stock['代码'], 'change_pct': change_pct, 'volume': volume})
    
    # 选最优1个
    if qualified:
        qualified.sort(key=lambda x: x['volume'], reverse=True)
        results[tier_name] = qualified[0]
    else:
        results[tier_name] = None

# 保存结果
output = {
    'date': data['date'],
    'emotion': data['emotion'],
    'results': results
}
with open('/tmp/lobster_bid_result.json', 'w') as f:
    json.dump(output, f, ensure_ascii=False, indent=2)

print("✅ 过滤完成")
```

---

## 🚨 禁止事项

1. **禁止独立分析候选股**
2. **禁止新增股票**
3. **只从盘前候选池过滤**
4. **必须更新关注股.md**

---

## ✅ 完成标志

- [ ] 候选池文件已确认存在（或补救完成）
- [ ] 竞价过滤已执行
- [ ] **已更新关注股.md（覆盖写入）**
- [ ] 已发送竞价选股消息
- [ ] 已写入临时复盘文件
- [ ] 已执行自动买入
- [ ] 已推送买入结果

---

## 最后步骤：回复用户（必须执行）

> **关键**：你已执行完所有步骤，生成了任务输出
> **必须**：立即回复用户，将结果完整发送给用户
> **禁止**：NO_REPLY、不回复、只写文件不推送

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
- 任务名使用本文件标题中的人类可读名称（如"竞价全流程""收盘综合"）
- 时间使用实际执行时间
- 关键结论只写本任务最重要的发现，不写流水账
- "给下个任务"必须是**可操作的参考**，下游任务真正能用上

---

## 合并历史

| 日期 | 版本 | 变更 |
|------|------|------|
| 2026-06-30 | v1 | 合并自 CRON_BID_RECOVERY_TASK.md(v1) + CRON_BID_TASK.md(v9) + CRON_BID_AUTO_BUY.md(v1)；去重交易日判断逻辑，保留各自核心步骤 |
