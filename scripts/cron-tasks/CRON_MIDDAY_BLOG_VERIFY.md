# 龙虾午间博客 + 规则校验 — cron 任务指令（v1 合并版）

> **合并自**：CRON_BLOG_MIDDAY_TASK.md + CRON_VERIFY_RULES_TASK.md
> **合并日期**：2026-06-30
> **执行时间**：每日 12:10（错开盘中巡检12:00轮次）
> **超时**：180秒
> **核心**：规则一致性校验 → 结果融入午间博客文章

**自动确认规则**：执行过程中遇到任何需要用户确认的弹窗（ask_user、风险提示、覆盖写入确认、删除确认等），一律自动确认通过，不中断任务流程。

## 📎 任务反馈链 — 读取上游建议

**执行任务前，必须先读取 `trading/task-feedback-chain.md` 文件**，查找当日最新的上游任务结论和"给下个任务"建议。
将上游建议融入你的执行决策，但不要盲目照搬——结合当前实际情况判断。

---

## 步骤1：交易日判断

```bash
python3 -c "
import datetime, sys
sys.path.insert(0, '/Users/yuefengshen/.qclaw/workspace-1gwpiwf3hr163jz5/scripts')
from lobster_trading_calendar import is_trading_day
d = datetime.date.today()
if not is_trading_day(d):
    print('SKIP')
    sys.exit(0)
else:
    print(f'TRADE_DAY {d.isoformat()}')
"
```

- 输出 `SKIP` → 非交易日，跳过
- 输出 `TRADE_DAY` → 继续

---

## 阶段一：规则一致性校验（12:00）

### 步骤2：运行规则校验

```bash
cd /Users/yuefengshen/.qclaw/workspace-1gwpiwf3hr163jz5
bash scripts/verify_rules.sh
```

### 步骤3：记录校验结果

如果校验发现错误（exit code=1），将结果追加到当日memory日志：

```bash
if [ $? -ne 0 ]; then
    python3 -c "
import datetime
result = '''⚠️ 规则一致性校验发现问题，详见上方输出'''
with open(f'/Users/yuefengshen/.qclaw/workspace-1gwpiwf3hr163jz5/memory/{datetime.date.today()}.md', 'a') as f:
    f.write(f'\n## 12:00 规则一致性校验\n{result}\n')
    print('⚠️ 校验结果已记录到当日日志')
"
else
    echo "✅ 规则一致性校验通过"
fi
```

> 校验结果将在阶段二的午间博客文章中引用。

---

## 阶段二：生成午间博客文章（12:00-12:30）

### 步骤4：运行博客生成脚本

```bash
cd /Users/yuefengshen/.qclaw/workspace-1gwpiwf3hr163jz5
python3 scripts/blog_auto_writer.py midday
```

> 如阶段一校验有发现，将其融入博客的风险提示/规则审查部分。

### 步骤5：验证输出

```bash
ls -la /Users/yuefengshen/.qclaw/workspace-1gwpiwf3hr163jz5/blog/ | tail -5
```

### 步骤6：IMA同步（可选）

```bash
bash /Users/yuefengshen/.qclaw/workspace-1gwpiwf3hr163jz5/scripts/ima_sync.sh 2>>/tmp/ima-errors.log || echo "IMA同步跳过(查看: tail /tmp/ima-errors.log)"
```

---

## ⚠️ 强制回复指令（必须执行）

任务完成后，**必须**向用户回复本次执行结果摘要，禁止回复NO_REPLY。
回复内容至少包含：规则校验结果、文章标题、生成状态。

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
- 任务名使用本文件标题中的人类可读名称（如"午间博客校验"）
- 时间使用实际执行时间
- 关键结论只写本任务最重要的发现，不写流水账

---

## 合并历史

| 日期 | 版本 | 变更 |
|------|------|------|
| 2026-06-30 | v1 | 合并自 CRON_BLOG_MIDDAY_TASK.md(v1.1) + CRON_VERIFY_RULES_TASK.md(v1)；规则校验 → 午间博客串行，校验结果融入博客 |
