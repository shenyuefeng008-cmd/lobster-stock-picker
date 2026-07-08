# 龙虾收盘博客文章 + IMA同步 — cron 任务指令（v1 合并版）

> **合并自**：CRON_BLOG_CLOSING_TASK.md + CRON_DAILY_IMA_SYNC_TASK.md
> **合并日期**：2026-06-30
> **执行时间**：每日 16:00（工作日）
> **超时**：300秒
> **核心**：IMA同步 → 生成收盘博客文章

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

## 阶段一：IMA知识库同步

> 将当天所有产出内容同步到IMA知识库「ai自动选股」。

### 同步内容清单

| 文件 | 说明 |
|------|------|
| `trading/news/YYYY-MM-DD.md` | 当日新闻（四个区） |
| `trading/BUG_LOG.md` | BUG日志（覆盖式更新） |
| `trading/模拟持仓.json` | 模拟持仓状态 |
| `trading/reports/closing_YYYYMMDD.md` | 收盘复盘报告（可选） |

### 执行同步脚本

```bash
bash /Users/yuefengshen/.qclaw/workspace-1gwpiwf3hr163jz5/scripts/daily_ima_sync.sh
```

等待完成（timeout=280s）。失败则告警。

### 输出结果

成功时输出：
```
☁️ 每日IMA同步 YYYY-MM-DD(16:00)完成
📰 新闻归档 ✅
🐛 BUG日志 ✅
💼 模拟持仓 ✅
```

---

## 阶段二：生成收盘博客文章

### 步骤2.1：运行博客生成脚本

```bash
cd /Users/yuefengshen/.qclaw/workspace-1gwpiwf3hr163jz5
python3 scripts/blog_auto_writer.py closing
```

### 步骤2.2：验证输出

```bash
ls -la /Users/yuefengshen/.qclaw/workspace-1gwpiwf3hr163jz5/blog/ | tail -5
```

---

## ⚠️ 强制回复指令（必须执行）

任务完成后，**必须**向用户回复本次执行结果摘要，禁止回复NO_REPLY。
回复内容至少包含：IMA同步状态、文章标题、生成状态。

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
- 任务名使用本文件标题中的人类可读名称（如"收盘博客同步"）
- 时间使用实际执行时间
- 关键结论只写本任务最重要的发现，不写流水账

---

## 合并历史

| 日期 | 版本 | 变更 |
|------|------|------|
| 2026-06-30 | v1 | 合并自 CRON_BLOG_CLOSING_TASK.md(v1.1) + CRON_DAILY_IMA_SYNC_TASK.md(v1)；IMA同步 → 收盘博客串行 |
