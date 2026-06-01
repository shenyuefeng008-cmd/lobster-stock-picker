# Task Summary 2026-05-21 模拟交易IMA同步

## Objective
用户要求将模拟持仓数据同步到IMA知识库，但格式有问题。

## Issues Found & Fixed
1. **总资产计算bug**：available在buy()时已扣除成本，但update_positions()的total=available+market_value，当market_value=0时total只有约51万。修复：total = available + 持仓成本总和
2. **持仓市值未更新**：market_value=0（收盘任务未运行update_positions），临时用成本价填充

## Actions
- 修复总资产计算逻辑
- 生成markdown格式持仓报告
- 通过ima_sync.sh同步到IMA（note_id: 7463003557464062）

## Current State
- 初始资金100万，5只持仓（成本约49万），可用51万
- 持仓：四方股份/华盛昌/华工科技(2.0板块卡位) + 中锐股份/金海高科(1.0分歧低吸)
- 全部2026-05-20买入，T+1锁定期
