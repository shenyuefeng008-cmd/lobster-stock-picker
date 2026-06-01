# 龙虾盘中巡检异常记录

## 任务目标
执行盘中巡检任务（13:30），按 `scripts/cron-tasks/CRON_INTRADAY_PATROL_TASK.md` 流程：交易日判断 → 运行 `lobster_intraday_patrol.py` → IMA 同步。

## 关键推理
1. **脚本崩溃原因**：`detect_buypoints()` 函数中调用 `adjust_position_pct(base_pct, pos_limit, len(positions))` 时，`positions` 变量尚未定义（应为列表，在函数内后续才会追加元素）。
2. **错误位置**：第371行，NameError。
3. **影响范围**：盘中巡检流程中断，无法完成买点检测、输出提醒文字、IMA 同步等后续步骤。

## 结论
- **状态**：❌ 执行失败
- **原因**：代码 bug（`positions` 变量作用域/时序问题）
- **修复建议**：检查 `detect_buypoints` 函数逻辑，确保 `positions` 在调用 `adjust_position_pct` 前已正确初始化（如 `positions = []` 并在循环中 `append`）。
- **后续**：修复后重新执行脚本，确保输出提醒文字（2-3句话）并完成 IMA 同步。

## 时间标签
2026-05-28 13:30 (Asia/Shanghai)
