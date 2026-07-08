# 龙虾买点监控 — cron 任务指令（v5）

> **频率**：每30分钟（10:00、10:30、13:00、13:30、14:00、14:30）
> **cron**：`0,30 10,13-14 * * 1-5 @ Asia/Shanghai`
> **超时**：120秒
> **核心**：数据采集 → 候选池移出 → 情绪判定 → 买点检测 → 简短输出

---

## ⚠️ 输出格式硬约束（违反则输出无效）

1. **仓位显示**：必须输出「仓位上限X成」或「仓位上限X0%」，**严禁**输出「仓位上限X%」
   - 正确：仓位上限5成 / 仓位上限50%
   - 错误：仓位上限5%（会被理解为5 percent = 0.05）
2. **情绪描述**：沿用emo_tag变量（🚨冰点→1.0 / ✅正常→1.0+3.0 / 🔥高潮→2.0+1.0 / 🔴极度高潮→辅助）
3. **禁止预测**：不出现「大概率」「应该会」「将」等词

## 步骤1：一键采集（前置校验+市场数据+关注股行情）

```bash
python3 << 'PYEOF'
import json, datetime, subprocess, re, sys

today = datetime.date.today().strftime('%Y-%m-%d')
errors = []

# 前置校验
for fp, label in [('/tmp/lobster_premarket_candidates.json','盘前候选池'), ('/tmp/lobster_watchlist_candidates.json','关注股'), ('/tmp/lobster_bid_result.json','竞价结果')]:
    try:
        with open(fp) as f: d = json.load(f)
        if d.get('date') != today: errors.append(f"{label}日期非今天")
    except Exception as e: errors.append(f"{label}: {e}")

# 市场数据
r = subprocess.run(["curl","-s","--max-time","10","https://qt.gtimg.cn/q=sh000001,sz399001,sz399006"], capture_output=True, timeout=12)
raw = r.stdout
for enc in ["gb2312","gbk","utf-8"]:
    try: txt = raw.decode(enc); break
    except: continue
else: txt = raw.decode("utf-8","replace")
indices = {}
for line in txt.split(";"):
    m = re.search(r'v_(\w+)="([^"]*)"', line)
    if m:
        p = m.group(2).split("~")
        if len(p) > 32: indices[p[1]] = {"price":p[3], "pct":p[32]}

r2 = subprocess.run(["curl","-s","-L","--max-time","10","-A","Mozilla/5.0","https://legulegu.com/stockdata/market-activity"], capture_output=True, text=True, timeout=12)
m2 = re.search(r'content="(2026-[^"]+)"', r2.stdout)
emo_text = m2.group(1) if m2 else "获取失败"

# 解析涨跌家数
mu = re.search(r'(\d+)家上涨', emo_text)
md = re.search(r'(\d+)家下跌', emo_text)
up = int(mu.group(1)) if mu else 0

# 关注股行情
watch_lines = []
try:
    with open("/Users/yuefengshen/.qclaw/workspace-1gwpiwf3hr163jz5/trading/关注股.md") as f:
        wl = f.read()
    codes = re.findall(r'(\d{6})', wl)
    if codes:
        ql = [f"sh{c}" if c.startswith('6') else f"sz{c}" for c in codes]
        r3 = subprocess.run(["curl","-s","--max-time","10",f"https://qt.gtimg.cn/q={','.join(ql)}"], capture_output=True, timeout=12)
        raw3 = r3.stdout
        for enc in ["gb2312","gbk","utf-8"]:
            try: txt3 = raw3.decode(enc); break
            except: continue
        else: txt3 = raw3.decode("utf-8","replace")
        for line in txt3.split(";"):
            m = re.search(r'v_(\w+)="([^"]*)"', line)
            if m:
                p = m.group(2).split("~")
                if len(p) > 32: watch_lines.append(f"  {p[1]}({m.group(1)[2:]}): {p[3]} ({p[32]}%)")
except: pass

# 输出面板
now_hm = datetime.datetime.now().strftime('%H:%M')
print(f"{'='*40}")
print(f"📊 买点监控 {now_hm}")
print(f"{'='*40}")

if errors:
    print(f"⚠️ 校验异常: {'; '.join(errors)}")

for name, d in indices.items():
    print(f"  {name}: {d['price']} ({d['pct']}%)")
print(f"  涨跌家数: {emo_text}")

if up < 1500: emo_tag = "🚨冰点→1.0"
elif up < 2500: emo_tag = "✅正常→1.0+3.0"
elif up < 3500: emo_tag = "🔥高潮→2.0+1.0"
else: emo_tag = "🔴极度高潮→辅助"
print(f"  情绪: {emo_tag}")

if watch_lines:
    print(f"\n  关注股:")
    for w in watch_lines: print(w)

# 保存供后续用
result = {"time": now_hm, "indices": indices, "emotion_text": emo_text, "up_count": up}
with open("/tmp/lobster_buypoint_data.json", "w") as f:
    json.dump(result, f, ensure_ascii=False)
PYEOF
```

## 步骤2：候选池日内移出（前置过滤）

> 每次买点监控先执行移出检查，清理失效候选，避免跟踪已无意义的标的

```bash
python3 << 'PYEOF'
import json, subprocess, re, datetime, sys, os

today = datetime.date.today().strftime('%Y-%m-%d')
changed = False

try:
    with open('/tmp/lobster_premarket_candidates.json') as f:
        data = json.load(f)
except:
    print("⚠️ 候选池文件不存在，跳过移出检查")
    sys.exit(0)

if data.get('date') != today:
    print("⚠️ 候选池日期非今天，跳过移出检查")
    sys.exit(0)

# 收集所有候选股代码（注意：候选在data['candidates']下）
candidates = data.get('candidates', data)  # 兼容两种格式
codes = []
for dim in ['1.0一进二', '1.0分歧低吸', '2.0板块卡位']:
    for item in candidates.get(dim, []):
        code = str(item.get('代码', item.get('code', '')))
        if code: codes.append((code, dim, item))

if not codes:
    print("候选池为空，无需移出")
    sys.exit(0)

# 批量查询行情
ql = [f"sh{c}" if c.startswith('6') else f"sz{c}" for c,_,_ in codes]
r = subprocess.run(["curl","-s","--max-time","10",f"https://qt.gtimg.cn/q={','.join(ql)}"], capture_output=True, timeout=12)
for enc in ["gb2312","gbk","utf-8"]:
    try: txt = r.stdout.decode(enc); break
    except: continue
else: txt = r.stdout.decode("utf-8","replace")

# 解析行情
quotes = {}
for line in txt.split(";"):
    m = re.search(r'v_(\w+)="([^"]*)"', line)
    if m:
        p = m.group(2).split("~")
        if len(p) > 37:
            code = p[2]  # 6位代码
            price = float(p[4])  # p[4]=当前价, p[3]=昨收
            pct = float(p[32])
            vol_wan = float(p[36])  # 万手
            amt_wan = float(p[37])  # 万元
            quotes[code] = {"price": price, "pct": pct, "vol_wan": vol_wan, "amt_wan": amt_wan}

# 移出检查
removed = []
removed_codes = []
now_hm = datetime.datetime.now().strftime('%H:%M')
for code, dim, item in codes:
    q = quotes.get(code)
    if not q:
        continue
    name = item.get('名称', item.get('name', code))
    reason = None

    # 条件1：涨停封住（涨幅≥9.8%且非ST）→ 移出（错过分歧低吸买点）
    limit_pct = 9.8 if not (code.startswith('688') or code.startswith('30')) else 19.8  # 创业板/科创板20%
    if q['pct'] >= limit_pct:
        reason = f"涨停封住({q['pct']:+.1f}%)，错过买点"

    # 条件2：跌幅>5% → 移出（破位）
    elif q['pct'] <= -5:
        reason = f"破位({q['pct']:+.1f}%)，不符合买入条件"

    if reason:
        # 从对应维度移除（注意：候选在data['candidates']下）
        for i, it in enumerate(candidates.get(dim, [])):
            if str(it.get('代码', it.get('code', ''))) == code:
                candidates[dim].pop(i)
                changed = True
                break
        removed.append(f"  ❌ {name}({code}) 移出 [{dim}]: {reason}")
        removed_codes.append(code)

# 条件3：14:30后未触发买点 → 清空当日候选池（当日失效）
if now_hm >= '14:30':
    total = sum(len(candidates.get(d, [])) for d in ['1.0一进二', '1.0分歧低吸', '2.0板块卡位'])
    if total > 0:
        for d in ['1.0一进二', '1.0分歧低吸', '2.0板块卡位']:
            candidates[d] = []
        changed = True
        removed.append(f"  🕐 14:30后清空候选池（{total}只标的当日失效）")

# 写回盘前候选池
if changed:
    with open('/tmp/lobster_premarket_candidates.json', 'w') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    
    # 同步到关注股JSON（如果存在）
    watch_path = '/tmp/lobster_watchlist_candidates.json'
    if os.path.exists(watch_path):
        try:
            with open(watch_path) as wf:
                watch_data = json.load(wf)
            if watch_data.get('date') == today:
                # 仅在关注股JSON的candidates下做同样的移除
                wc = watch_data.get('candidates', {})
                for dim in ['1.0一进二', '1.0分歧低吸', '2.0板块卡位', '3.0趋势低吸']:
                    watch_data['candidates'][dim] = [s for s in wc.get(dim, []) if str(s.get('代码', s.get('code', ''))) not in removed_codes]
                watch_data['移出同步'] = now_hm
                with open(watch_path, 'w') as wf:
                    json.dump(watch_data, wf, ensure_ascii=False, indent=2)
                print("✅ 关注股JSON已同步移出")
        except Exception as e:
            print(f"⚠️ 关注股JSON同步失败: {e}")

if removed:
    print(f"\n🔔 关注股变动 | 移出 ({now_hm})")
    print("─" * 30)
    for r in removed: print(r)
    print(f"\n📊 候选池剩余: {sum(len(candidates.get(d, [])) for d in ['1.0一进二', '1.0分歧低吸', '2.0板块卡位', '3.0趋势低吸'])}只")
else:
    print("📋 关注股无变动，候选池全部有效")
PYEOF
```

## 步骤3：买点检测 + 自动买入

调用 `lobster_buypoint_detector.py` 自动检测买点并写入模拟交易仓：
```bash
python3 /Users/yuefengshen/.qclaw/workspace-1gwpiwf3hr163jz5/scripts/lobster_buypoint_detector.py
```

**检测逻辑**（脚本内部实现）：
- 1.0分歧低吸：回踩MA5/MA10 + 缩量企稳 → 自动买入10%仓位
- 2.0板块卡位：板块涨停≥3 + 个股前排 → 自动买入10%仓位
- 3.0趋势低吸：回踩MA5不破 + 涨跌家数>2500 → 自动买入15%仓位

**输出格式硬约束**：
- ✅ 正确："仓位上限5成" / "建议仓位10%"
- ❌ 错误："仓位上限5%"（会被误解为0.05%）
- 禁止在输出中使用"X%"表示仓位上限，必须用"X成"或"X%"表示具体仓位比例

## 步骤4：读取买点通知 → 推送用户

有买点触发时，`lobster_buypoint_detector.py` 会保存通知到 `/tmp/lobster_buy_notification_{today}.txt`。

读取并输出给用户：
```bash
PYTHON_READ_NOTIFY=$(python3 -c "
import datetime, json
today = datetime.date.today().strftime('%Y%m%d')
import os
nf = f'/tmp/lobster_buy_notification_{today}.txt'
if os.path.exists(nf):
    with open(nf) as f:
        print(f.read())
else:
    print('')
")
if [ -n "$PYTHON_READ_NOTIFY" ]; then
    echo ""
    echo "📢 买点通知:"
    echo "$PYTHON_READ_NOTIFY"
fi
```

**输出要求**（买点触发时）：
- 必须输出以上买点通知内容，**不得省略/截断**
- 格式：🔥 维度 股票名(代码): 买入理由
- 包含可用资金和总成本状态
- **模拟买入**：每个买点触发后调用 simulated_trading.buy()，传入 up_count 参数控制仓位

### 模拟买入集成

买点触发后执行模拟买入（在通知输出后追加）：

```python
import sys, json, re, datetime
sys.path.insert(0, "/Users/yuefengshen/.qclaw/workspace-1gwpiwf3hr163jz5/scripts")
from simulated_trading import buy

# 从步骤1获取涨跌家数
up_count = 0
try:
    with open("/tmp/lobster_buypoint_data.json") as f:
        bp_data = json.load(f)
    up_count = bp_data.get("up_count", 0)
except: pass

# 从买点通知提取触发股票
today_str = datetime.date.today().strftime('%Y-%m-%d')
try:
    with open(f"/tmp/lobster_buy_notification_{today_str.replace('-','')}.txt") as f:
        notify = f.read()
    for line in notify.strip().split("\n"):
        m = re.match(r".+ (.+?) \((\d{6})\): (.+)", line)
        if m:
            name, code, reason = m.groups()
            # 获取实时价格（从关注股行情或实时接口）
            try:
                import subprocess
                q = f"sh{code}" if code.startswith("6") else f"sz{code}"
                r = subprocess.run(["curl","-s","--max-time","10",f"https://qt.gtimg.cn/q={q}"], capture_output=True, timeout=12)
                raw = r.stdout
                for enc in ["gb2312","gbk","utf-8"]:
                    try: txt = raw.decode(enc); break
                    except: continue
                pp = txt.split("~")
                price = float(pp[4]) if len(pp) > 4 else 0  # pp[4]=当前价
                dimension = "1.0分歧低吸"  # 或根据通知内容判断
                result = buy(code, name, price, reason, dimension, up_count=up_count)
                print(result)
            except Exception as e:
                print(f"获取{code}价格失败: {e}")
except: pass
```

**输出要求**（无买点触发时）：
- 2-3句话简要汇报：情绪面板 + 候选池状态

---

**版本**：v6（增加买点通知推送）
**更新**：2026-05-20 14:46

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
