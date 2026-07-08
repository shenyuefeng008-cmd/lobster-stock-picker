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

### Step 1：检查今天是否为交易日

```bash
TODAY=$(date +%Y-%m-%d)
DOW=$(date +%u)  # 1=周一 6=周六 7=周日
CAL=/Users/yuefengshen/.qclaw/workspace-1gwpiwf3hr163jz5/trading/交易日历.md

# 周末直接跳过
if [ "$DOW" -ge 6 ]; then echo "周末非交易日"; exit 0; fi

# 检查是否在休市日历中
if grep -q "$TODAY" "$CAL"; then
  # 再确认是休市行而非调休开市行
  if grep "$TODAY" "$CAL" | grep -q "调休"; then
    echo "调休开市日，继续执行"
  else
    echo "节假日休市，跳过"; exit 0
  fi
fi
echo "交易日，继续执行"
```

若非交易日则结束；交易日 → 继续。

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
