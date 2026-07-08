# 龙虾BUG_LOG周日回顾 2026-06-21

## 任务目标
按CRON_BUG_LOG_REVIEW.md指令，回顾BUG_LOG.md中P0/P1条目，检查近7天是否复现

## 关键发现
- BUG_LOG共61条（18原始BUG + 9 ERROR + 34条BUG-010/012回归记录）
- BUG-058/059（6/20发现）是BUG-010/012反复回归30+次的真正根因：`sell_partial()`未调用`_update_capital_after_trade()` + 用`initial_capital`算仓位
- 6/18~19日志中仍有trade_log脏数据遗留（hist_pnl与逐笔加总不符）
- 其余24条原始BUG/ERROR本周未复现

## 结论
- 根因代码层面已修复（BUG-058/059），但需下周实盘连续5日验证
- trade_log历史脏数据仍待处理
- 报告已写入 /tmp/lobster_bug_review_2026-06-21.md
