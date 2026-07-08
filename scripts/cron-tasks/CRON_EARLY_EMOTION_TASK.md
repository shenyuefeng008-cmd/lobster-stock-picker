# 龙虾早盘情绪快速检测 — cron 任务指令（v1）

> **频率**：每个交易日 09:45
> **cron**：`45 9 * * 1-5 @ Asia/Shanghai`
> **超时**：60秒
> **核心**：检测竞价后情绪是否从辅助模式回落，弥补 09:25-10:00 监控空白

**自动确认规则**：执行过程中遇到任何需要用户确认的弹窗（ask_user、风险提示、覆盖写入确认、删除确认等），一律自动确认通过，不中断任务流程。
## 📎 任务反馈链 — 读取上游建议

**执行任务前，必须先读取 `trading/task-feedback-chain.md` 文件**，查找当日最新的上游任务结论和"给下个任务"建议。
将上游建议融入你的执行决策，但不要盲目照搬——结合当前实际情况判断。

- 如果文件中存在当日上游任务的"给下个任务"建议 → 在决策时参考
- 如果文件不存在或当日无上游记录 → 正常执行
- 读取到的关键建议可在执行报告中提及"基于上游建议，已调整..."
---

## 背景

竞价（09:25）时情绪可能>3500进入辅助模式，但开盘后情绪可能快速回落到可操作区间。
09:45快速检测填补了这个空白，如果情绪回落立即通知用户可以操作。

## 步骤0：交易日判断（⚠️ 必须用exec执行，禁止AI自行判断）

**你必须使用exec工具执行以下命令，禁止自行判断是否交易日！**

```bash
python3 -c "
import datetime, sys
sys.path.insert(0, '/Users/yuefengshen/.qclaw/workspace-1gwpiwf3hr163jz5/scripts')
from lobster_trading_calendar import is_trading_day
d = datetime.date.today()
if not is_trading_day(d):
    print('SKIP')
else:
    print('TRADE_DAY')
"
```

- 输出 `TRADE_DAY` → 继续步骤1
- 输出 `SKIP` → 回复用户「📊 非交易日，早盘情绪快检跳过」

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
    mode = "辅助模式，仓位上限10-20%，不追板"
    actionable = False
elif up > 2500:
    emo_tag = "🔥高潮→2.0+1.0"
    mode = "2.0+1.0主导，仓位上限50-70%"
    actionable = True
elif up > 2000:
    emo_tag = "✅正常→1.0+3.0"
    mode = "1.0+3.0主导，仓位上限90%"
    actionable = True
elif up > 1500:
    emo_tag = "⚠️偏弱→1.0主导"
    mode = "1.0主导，仓位上限30%"
    actionable = True
else:
    emo_tag = "🚨冰点→1.0主导"
    mode = "1.0主导，仓位上限30%，不追板"
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
- **仓位显示**：必须用"X%"，禁止"X成"表示仓位上限

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
