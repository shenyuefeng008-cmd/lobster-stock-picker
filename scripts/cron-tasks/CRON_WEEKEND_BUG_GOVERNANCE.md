# 龙虾周末Bug治理 — cron 任务指令（v1 合并版）

> **合并自**：CRON_WEEKLY_BUGFIX_TASK.md + CRON_BUG_LOG_REVIEW.md
> **合并日期**：2026-06-30
> **执行时间**：周六 20:00
> **核心任务**：Bug修复巡检(周六) → BUG_LOG回顾(周日21:00)，同一个文件内串行
> **超时**：600秒
> ⚠️ **绝对禁止只记录不修复**：发现问题必须当场修，修完必须验证
> ⚠️ 本任务在周末触发，非交易日，不依赖实时市场数据

**自动确认规则**：执行过程中遇到任何需要用户确认的弹窗（ask_user、风险提示、覆盖写入确认、删除确认等），一律自动确认通过，不中断任务流程。

## 📎 任务反馈链 — 读取上游建议

**执行任务前，必须先读取 `trading/task-feedback-chain.md` 文件**，查找当日最新的上游任务结论和"给下个任务"建议。
将上游建议融入你的执行决策，但不要盲目照搬——结合当前实际情况判断。

---

## 执行前必读

1. 读取 `lobster-rules.md` 和 `lobster-config.json` 了解当前规则和参数
2. 读取 `trading/BUG_LOG.md` 了解已知Bug清单
3. 读取最近7天 `memory/YYYY-MM-DD.md` 了解近期问题

---

## 阶段一：Bug修复巡检（周六 20:00）

### 🔍 四维Bug扫描

#### 维度1：代码逻辑Bug

扫描 `scripts/` 下所有Python脚本：

1. **语法检查**：`python3 -c "import ast; ast.parse(open(f).read())"` 对每个.py文件
2. **函数入口校验**：检查 `buy()/sell()/sell_partial()` 是否都有交易日+交易时段校验
3. **字段命名一致性**：搜索 `current_pnl` / `floating_pnl` 等已废弃字段，如有则修复为 `total_pnl`/`today_pnl`
4. **除零风险**：搜索 `/ p[` 或 `/ data[` 等可能除零的地方
5. **JSON读写安全**：检查 `_load()/_save()` 是否有文件损坏恢复机制

#### 维度2：数据一致性Bug

1. **资金账本**：
   - `total_assets == available + market_value`（逐持仓现价计算）
   - `hist_pnl == trade_log卖出pnl加总`
   - `floating_pnl == 逐持仓(现价-成本)*股数加总`
   - 不一致则执行 `validate_capital.py` 自动修正

2. **持仓完整性**：
   - 持仓中每只股票的 `cost` 字段 = shares * buy_price + 买入手续费
   - `can_sell` 状态是否正确（T+1规则）
   - 是否有"幽灵持仓"（持仓中有但trade_log无买入记录）

3. **trade_log完整性**：
   - 每笔SELL是否有对应的BUY
   - 同一股票买卖股数是否匹配（未清仓的应在持仓中）
   - `amount`/`pnl`/`pnl_pct` 计算是否正确

#### 维度3：Cron任务Bug

1. **任务注册验证**：所有 `scripts/cron-tasks/CRON_*.md`（非DEPRECATED）是否有对应注册
2. **任务输出验证**：检查最近一次运行是否产生了预期输出文件
3. **关键链路**：盘前选股→竞价过滤→买入→盘中巡检→收盘复盘，是否有断点

#### 维度4：配置/规则一致性Bug

1. **Config vs 代码**：`lobster-config.json` 中的参数是否被代码正确读取（如止损%、仓位%）
2. **规则 vs 实际**：`lobster-rules.md` 中描述的规则是否与代码实现一致
3. **交易日历**：`config/trading_calendar.json` 中的假期是否被所有需要的地方引用

### 🔧 修复执行规则

1. **发现Bug → 当场修复**：修改代码/数据，不允许只记录
2. **修复后必须验证**：重跑对应检查项，确认修复成功
3. **修复失败 → 最多重试3次**，仍失败则记录到 `memory/YYYY-MM-DD.md` 标注 `🐛 待人工介入`
4. **参数修改必须更新config**：修改数值参数 → `lobster-config.json`，禁止hardcode
5. **新发现的Bug追加到 `trading/BUG_LOG.md`**：格式 `BUG-XXX: 描述 | 根因 | 修复 | 预防`

### 输出：Bug修复报告

修复完成后，将结果写入 `trading/reports/weekly_bugfix_YYYY-MM-DD.md`：

```markdown
# 龙虾周六Bug修复巡检 YYYY-MM-DD

## 扫描结果
- 维度1 代码逻辑：X个Bug（Y个已修复，Z个待人工）
- 维度2 数据一致性：X个Bug
- 维度3 Cron任务：X个Bug
- 维度4 配置一致性：X个Bug

## 修复明细
| # | Bug | 维度 | 修复动作 | 验证结果 |
|---|-----|------|---------|---------|
| 1 | 描述 | 维度N | 具体修改 | ✅/❌ |

## 系统健康度
A/B/C/D 评级
```

---

## 阶段二：BUG_LOG周日回顾（周日 21:00）

> 本阶段在周日执行，回顾BUG_LOG中P0/P1条目是否在近期复现。

### 步骤2.1：读取BUG_LOG.md

```bash
BUG_LOG="/Users/yuefengshen/.qclaw/workspace-1gwpiwf3hr163jz5/trading/BUG_LOG.md"
if [ -f "$BUG_LOG" ]; then
    echo "📋 BUG_LOG 已找到，开始回顾检查..."
    grep -E "^## (BUG-|ERROR-)" "$BUG_LOG" | head -20
else
    echo "⚠️ BUG_LOG.md 不存在，跳过回顾"
    exit 0
fi
```

### 步骤2.2：检查最近7天memory日志

```bash
# 获取最近7天日期
for i in {0..6}; do
    date -d "-$i day" +%Y-%m-%d 2>/dev/null || date -v-${i}d +%Y-%m-%d
done
```

对BUG_LOG.md中每条P0/P1记录：
1. 读取该BUG的「根因」和「预防措施」
2. 检查最近7天的 `memory/YYYY-MM-DD.md` 日志
3. 搜索是否有同类错误复现（关键词匹配根因）
4. 决策：✅ 未复现 / ⚠️ 疑似复现 / ❌ 已复现

### 步骤2.3：生成回顾报告

将结果写入 `/tmp/lobster_bug_review_YYYY-MM-DD.md`：

```markdown
# 龙虾BUG_LOG周日回顾 YYYY-MM-DD

## 检查概要
- 检查条目：X条P0/P1
- 未复现：X条
- 疑似复现：X条
- 已复现：X条

## 详细结果

### ✅ 未复现
- BUG-XXX：原因（未出现同类错误）

### ⚠️ 疑似复现
- BUG-XXX：原因（X月X日日志中发现类似情况）

### ❌ 已复现
- BUG-XXX：原因（X月X日确认复现）→ 已修复

## 建议
- 无 / 需要重点关注BUG-XXX
```

### 步骤2.4：向用户汇报

```
✅ 龙虾BUG_LOG周日回顾已完成（YYYY-MM-DD）
- 检查条目：X条P0/P1
- 未复现：X条
- 疑似复现：X条
- 已复现：X条
```

---

## 同步

修复完成后执行乐享同步：
```bash
```

---

## 向用户汇报

```
🔧 龙虾周末Bug治理已完成
- 发现X个Bug，已修复Y个，待人工Z个
- 系统健康度：A/B/C/D
- BUG_LOG回顾：X条P0/P1，复现Z条
- 详细报告：trading/reports/weekly_bugfix_YYYY-MM-DD.md
```

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
- 任务名使用本文件标题中的人类可读名称（如"周末Bug治理"）
- 时间使用实际执行时间
- 关键结论只写本任务最重要的发现，不写流水账

---

## 合并历史

| 日期 | 版本 | 变更 |
|------|------|------|
| 2026-06-30 | v1 | 合并自 CRON_WEEKLY_BUGFIX_TASK.md(v1) + CRON_BUG_LOG_REVIEW.md(v1)；周六巡检→周日回顾同一文件内串行 |
