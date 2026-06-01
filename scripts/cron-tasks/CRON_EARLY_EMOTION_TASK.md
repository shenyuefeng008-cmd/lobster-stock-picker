# 龙虾早盘情绪快速检测 — cron 任务指令（v1）

> **频率**：每个交易日 09:45
> **cron**：`45 9 * * 1-5 @ Asia/Shanghai`
> **超时**：60秒
> **核心**：检测竞价后情绪是否从辅助模式回落，弥补 09:25-10:00 监控空白

---

## 背景

竞价（09:25）时情绪可能>3500进入辅助模式，但开盘后情绪可能快速回落到可操作区间。
09:45快速检测填补了这个空白，如果情绪回落立即通知用户可以操作。

## 步骤1：采集情绪数据

```bash
python3 << 'PYEOF'
import json, datetime, subprocess, re, sys

# 前置：检查是否交易日
today = datetime.date.today().strftime('%Y-%m-%d')
weekday = datetime.date.today().weekday()
if weekday >= 5:
    print("非交易日，跳过")
    sys.exit(0)

# 获取涨跌家数
r = subprocess.run(["curl","-s","-L","--max-time","15","-A","Mozilla/5.0","https://legulegu.com/stockdata/market-activity"], capture_output=True, text=True, timeout=20)
text = r.stdout

# 解析
mu = re.search(r'(\d+)家上涨', text)
md = re.search(r'(\d+)家下跌', text)
mzt = re.search(r'(\d+)家涨停', text)
mdt = re.search(r'(\d+)家跌停', text)

up = int(mu.group(1)) if mu else 0
down = int(md.group(1)) if md else 0
zt = int(mzt.group(1)) if mzt else 0
dt = int(mdt.group(1)) if mdt else 0

# 情绪判定
if up > 3500:
    emo_tag = "🔴极度高潮→辅助"
    mode = "辅助模式，仓位上限1-2成，不追板"
    actionable = False
elif up > 2500:
    emo_tag = "🔥高潮→2.0+1.0"
    mode = "2.0+1.0主导，仓位上限5-7成"
    actionable = True
elif up > 2000:
    emo_tag = "✅正常→1.0+3.0"
    mode = "1.0+3.0主导，仓位上限9成"
    actionable = True
elif up > 1500:
    emo_tag = "⚠️偏弱→1.0主导"
    mode = "1.0主导，仓位上限5成"
    actionable = True
else:
    emo_tag = "🚨冰点→1.0主导"
    mode = "1.0主导，仓位上限5成，不追板"
    actionable = True

now_hm = datetime.datetime.now().strftime('%H:%M')
print(f"📊 早盘情绪快检 {now_hm}")
print(f"{'='*40}")
print(f"  涨跌家数: {up}:{down}")
print(f"  涨停{zt}只 跌停{dt}只")
print(f"  情绪: {emo_tag}")
print(f"  {mode}")

# 读取竞价时情绪（对比）
prev_emo = "未知"
try:
    with open('/tmp/lobster_watchlist_candidates.json') as f:
        wd = json.load(f)
    prev_emo = wd.get('emotion', {}).get('上涨家数', '未知')
    print(f"  竞价时情绪: {prev_emo}家上涨")
except: pass

# 关键判断：情绪是否从辅助模式回落
if actionable and str(prev_emo) != '未知':
    prev_up = int(prev_emo) if isinstance(prev_emo, (int, str)) and str(prev_emo).isdigit() else 0
    if prev_up > 3500:
        print(f"\n🔔 情绪回落！从辅助模式(>{prev_up})→可操作区间({up})")
        print(f"  操作窗口打开，可关注买点监控候选标的")
    elif prev_up > 2500 and up <= 2500:
        print(f"\n🔔 情绪回落！从高潮({prev_up})→中性({up})")
elif not actionable:
    print(f"\n  仍在辅助模式，等10:00买点监控正常触发")

# 保存供买点监控使用
result = {"time": now_hm, "up_count": up, "down_count": down, "zt": zt, "dt": dt, "emo_tag": emo_tag, "actionable": actionable}
with open("/tmp/lobster_early_emotion.json", "w") as f:
    json.dump(result, f, ensure_ascii=False)
PYEOF
```

## 输出规则

- **情绪回落到可操作区间**：输出🔔通知 + 可操作维度 + 候选标的提示
- **仍在辅助模式**：1句话说明，等10:00正常触发
- **禁止预测**：不出现"大概率""应该会"
- **仓位显示**：必须用"X成"，禁止"X%"表示仓位上限

---

**版本**：v1
**创建**：2026-05-25


## 最后步骤：回复用户（必须执行）

> **关键**：你已执行完所有步骤，生成了任务输出
> **必须**：立即回复用户，将结果完整发送给用户
> **禁止**：NO_REPLY、不回复、只写文件不推送
>
> 回复格式：
> ```
> [任务对应的输出内容]
> ```
