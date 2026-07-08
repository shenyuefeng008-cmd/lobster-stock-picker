# 龙虾竞价兜底 — cron 任务指令（v1 新增）

> **触发条件**：`/tmp/lobster_premarket_candidates.json` 不存在
> **执行时间**：交易日 09:20
> **作用**：如果07:00盘前任务未成功写入候选池文件，立即补救，确保09:25竞价过滤能执行

**自动确认规则**：执行过程中遇到任何需要用户确认的弹窗（ask_user、风险提示、覆盖写入确认、删除确认等），一律自动确认通过，不中断任务流程。
## 📎 任务反馈链 — 读取上游建议

**执行任务前，必须先读取 `trading/task-feedback-chain.md` 文件**，查找当日最新的上游任务结论和"给下个任务"建议。
将上游建议融入你的执行决策，但不要盲目照搬——结合当前实际情况判断。

- 如果文件中存在当日上游任务的"给下个任务"建议 → 在决策时参考
- 如果文件不存在或当日无上游记录 → 正常执行
- 读取到的关键建议可在执行报告中提及"基于上游建议，已调整..."
## 前置检查

用exec执行：`ls -la /tmp/lobster_premarket_candidates.json 2>/dev/null && echo EXISTS || echo MISSING`

- 如果输出 `EXISTS` → **文件已存在，无需补救，退出并回复"盘前候选池正常，无需操作"**
- 如果输出 `MISSING` → 继续执行以下步骤

## 步骤1：重新运行盘前选股引擎（核心补救）

用exec执行：

```
python3 /Users/yuefengshen/.qclaw/workspace-1gwpiwf3hr163jz5/scripts/lobster_premarket_engine.py 2>&1
```

**必须确认**：命令执行完成后，`/tmp/lobster_premarket_candidates.json` 已存在。

## 步骤2：读取并汇报结果

用exec执行 `cat /tmp/lobster_premarket_candidates.json`，然后发送告警消息：

```
⚠️ 【盘前选股补救 09:20】
07:00盘前任务未成功，已自动补救。
候选池文件已重新生成，今日候选股如下：

[候选池内容]
```

## 步骤3：运行竞价过滤

构造竞价过滤输入文件，用exec执行：

```python
python3 -c "
import json, urllib.request, ssl, datetime

# 构造bid_input
with open('/tmp/lobster_premarket_candidates.json') as f:
    data = json.load(f)

# 获取当前情绪
ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE
req = urllib.request.Request('https://legulegu.com/stockdata/market-activity',
    headers={'User-Agent': 'Mozilla/5.0'})
import re
try:
    resp = urllib.request.urlopen(req, timeout=15, context=ctx)
    content = resp.read().decode('utf-8', errors='replace')
    md = re.search(r'上涨:(\d+)\s*下跌:(\d+)', content)
    up = int(md.group(1)) if md else 0
    down = int(md.group(2)) if md else 0
except:
    up = down = 0

bid_input = {
    'date': datetime.date.today().strftime('%Y-%m-%d'),
    'candidates': data['candidates'],
    'emotion': {'up': up, 'down': down},
    'timestamp': datetime.datetime.now().isoformat()
}
with open('/tmp/lobster_bid_input.json', 'w') as f:
    json.dump(bid_input, f, ensure_ascii=False)
print('bid_input created')
"
```

然后执行竞价过滤：

```
python3 /Users/yuefengshen/.qclaw/workspace-1gwpiwf3hr163jz5/scripts/lobster_bid_filter_v2.py 2>&1
```

## 步骤4：执行自动买入（如有竞价通过标的）

读取 `/tmp/lobster_bid_result.json`，如果有通过标的，按 CRON_BID_AUTO_BUY.md 执行买入。

## ✅ 完成标志

- [ ] 候选池文件已存在
- [ ] 竞价过滤已执行
- [ ] 结果已汇报用户

**任务版本**：v1
**创建日期**：2026-06-03
**触发原因**：连续两天盘前任务汇报成功但文件未生成，根因为bash代码块agent不执行

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
