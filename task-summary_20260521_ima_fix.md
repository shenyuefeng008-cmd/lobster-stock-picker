# Task Summary 2026-05-21 IMA同步修复

## 问题
盘前选股同步到IMA时内容不全，缺失情绪面板数据和候选股详情。

## 根因
CRON_PREMARKET_TASK.md的步骤3只调ima_sync.sh，但没指定如何生成md文件内容。
cron执行时AI自行构造的md文件字段名与JSON不匹配（用了英文key而非中文key）。

## 修复
1. 步骤3改为"写入IMA同步文件+同步"，用Python脚本从JSON生成完整md：
   - emotion字段：上涨家数/下跌家数/涨停/跌停/主导维度/辅助维度/总仓位上限
   - candidates字段：名称/代码/备注/额/板块
2. 重新同步了2026-05-21完整数据（note_id=7463018275285469）

## 另外完成
- 个股仓位动态调整：calc_stock_factor()基于总市值/成交额/换手率调整仓位系数(0.3~1.5)
- 情绪仓位控制：check_position_limit() + emotion_force_sell()
- CRON_BUYPOINT_TASK.md：买点触发后调用buy(up_count=...)
- CRON_SELLPOINT_TASK.md：卖点+情绪强制减仓
