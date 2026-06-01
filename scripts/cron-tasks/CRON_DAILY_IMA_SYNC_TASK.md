# 每日IMA同步任务

> **版本**：v1.0
> **创建日期**：2026-05-31
> **执行频率**：每交易日 16:00（收盘后）
> **超时**：300s

## 任务目标

将当天所有产出内容同步到IMA知识库「ai自动选股」，实现永久存档。

## 同步内容清单

| 文件 | 说明 |
|------|------|
| `trading/news/YYYY-MM-DD.md` | 当日新闻（四个区） |
| `trading/BUG_LOG.md` | BUG日志（覆盖式更新） |
| `trading/模拟持仓.json` | 模拟持仓状态 |
| `trading/reports/closing_YYYYMMDD.md` | 收盘复盘报告（可选） |

## AI Agent执行指令

### Step  检查今天是否为交易日


```bash;cat /Users/yuefengshen/.qclaw/workspace-1gwpiwf3hr163jz5/trading/交易日历.md | grep "$(date +%Y-%m-%d)"
```

若找到且非节假日 →  继续；否则结束。

### Step2：执行同步脚本


```bash();bash /Users/yuefengshen/.qclaw/workspace-1gwpiwf3hr163jz5/scripts/daily_ima_sync.sh 
```

等待完成（timeout=280s）。失败则告警。

### Step3：输出结果并回复用户


成功时输出：

```
☁️  每日IMA同步 YYYY-MM-DD(16:00)完成 —
📰  新闻归档 → note_id=xxx media_id=xxx ✅  
🐛 BUG日志 → note_id=xxx media_id=xxx ✅  
💼  模拟持仓 → note_id=xxx media_id=xxx ✅  

```

有收盘复盘报告时追加一行。部分失败输出警告，全部失败输出错误并告警。

**禁止NO_REPLY —必须回复用户。
