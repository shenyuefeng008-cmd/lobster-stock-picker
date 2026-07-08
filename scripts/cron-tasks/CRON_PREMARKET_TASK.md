# 龙虾盘前选股 — cron 任务指令（v7 执行优先版）

> **执行时间**：交易日 07:00
> **核心任务**：运行选股引擎 → 发送结果 → 更新关注股
> **v7变更**：所有操作改为agent直接执行步骤，禁止用bash heredoc代码块

**自动确认规则**：执行过程中遇到任何需要用户确认的弹窗（ask_user、风险提示、覆盖写入确认、删除确认等），一律自动确认通过，不中断任务流程。
## 📎 任务反馈链 — 读取上游建议

**执行任务前，必须先读取 `trading/task-feedback-chain.md` 文件**，查找当日最新的上游任务结论和"给下个任务"建议。
将上游建议融入你的执行决策，但不要盲目照搬——结合当前实际情况判断。

- 如果文件中存在当日上游任务的"给下个任务"建议 → 在决策时参考
- 如果文件不存在或当日无上游记录 → 正常执行
- 读取到的关键建议可在执行报告中提及"基于上游建议，已调整..."
## 步骤1（核心，必须先执行）

用exec工具执行以下命令，运行选股引擎：

```
python3 /Users/yuefengshen/.qclaw/workspace-1gwpiwf3hr163jz5/scripts/lobster_premarket_engine.py
```

**必须确认**：命令执行完成后，检查 `/tmp/lobster_premarket_candidates.json` 是否存在。
- 如果不存在 → 立即报错，停止后续步骤
- 如果存在 → 继续步骤1.5

### 步骤1.5：持久化候选池（P0-1修复）

> 将候选池持久化到 `trading/candidates/` 目录，消除 /tmp 单点故障。

```bash
python3 -c "
import json, datetime, os, shutil
today = datetime.date.today().strftime('%Y-%m-%d')
src = '/tmp/lobster_premarket_candidates.json'
dst_dir = '/Users/yuefengshen/.qclaw/workspace-1gwpiwf3hr163jz5/trading/candidates'
os.makedirs(dst_dir, exist_ok=True)
dst = f'{dst_dir}/premarket_{today}.json'
shutil.copy2(src, dst)
print(f'✅ 候选池已持久化: {dst}')
"
```

## 步骤2：读取结果并格式化发送

用exec执行 `cat /tmp/lobster_premarket_candidates.json`，读取JSON结果，然后按以下格式发送消息给用户：

```
✅ 龙虾盘前选股 YYYY-MM-DD

📰 舆情/催化速览
（从JSON的news_sentiment和candidates备注中提取关键信息，1-2行）

- 情绪：XXX涨/XXX跌，XXX涨停/XXX跌停
- 主导维度：X，辅助维度：Y
- 总仓位上限：X%

【1.0一进二候选池】（X只）
1. 股票(代码) — 备注（含🔴催化标注）
...

【1.0分歧低吸候选池】（X只）
...

【2.0板块卡位候选池】（X只）
...

【3.0趋势低吸候选池】（X只）⛔冰点·3.0熔断（如适用）
...

---
📌 🔴标记为7日内有催化事件，09:25竞价阶段将从中筛选最优1只/档位
```

## 步骤3：催化剂注入

用exec执行以下命令（步骤1成功后，步骤1的输出已包含候选池，无需额外输入）：

```
python3 /Users/yuefengshen/.qclaw/workspace-1gwpiwf3hr163jz5/scripts/enrich_candidates_with_news.py
```

此步骤会在候选池JSON中标注🔴有催化的股票，失败则跳过。

## 步骤4：更新关注股

用exec执行以下命令更新 `trading/关注股.md`：

```
python3 -c "
import json
today = __import__('datetime').date.today().strftime('%Y-%m-%d')
with open('/tmp/lobster_premarket_candidates.json') as f:
    data = json.load(f)
lines = [f'# 关注股 {today}', '', '## 候选池（盘前版）', '']
for dim, stocks in data['candidates'].items():
    lines.append(f'### {dim}')
    for s in stocks:
        code = s.get('代码', s.get('code','?'))
        name = s.get('名称', s.get('name','?'))
        note = s.get('备注', '')
        lines.append(f'- {name}({code}) — {note}')
    lines.append('')
with open('/Users/yuefengshen/.qclaw/workspace-1gwpiwf3hr163jz5/trading/关注股.md', 'w', encoding='utf-8') as f:
    f.write('\n'.join(lines))
print('✅ 关注股.md已更新')
"
```

## 步骤5：解锁T+1

用exec执行：

```
python3 -c "import sys; sys.path.insert(0,'/Users/yuefengshen/.qclaw/workspace-1gwpiwf3hr163jz5/scripts'); from simulated_trading import unlock_t1; print(unlock_t1())"
```

## ✅ 完成标志

- [ ] 步骤1：脚本执行成功，JSON已生成
- [ ] 步骤2：结果已发送给用户
- [ ] 步骤4：关注股.md已更新
- [ ] 步骤6：T+1已解锁

---

## ❌ 禁止事项

1. **禁止**在步骤1之前生成任何选股结果（禁止用内部知识合成摘要）
2. **禁止**跳过步骤1直接进入后续步骤
3. **禁止**修改候选池内容

**任务版本**：v7（重写为执行优先版）
**最后更新**：2026-06-03

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
