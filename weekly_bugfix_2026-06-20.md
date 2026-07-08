# 龙虾周六Bug修复巡检 2026-06-20

## 执行摘要
四维扫描完成，发现4个Bug全部当场修复。关键发现：BUG-010/012反复回归30+次的根因是 `sell_partial()` 缺少 `_update_capital_after_trade()` 调用，已结构性修复。

## 修复清单
1. **BUG-058**（维度1）：sell_partial() 未调用 _update_capital_after_trade() — BUG-010/012回归根因，已修复
2. **BUG-059**（维度1）：sell_partial() position_pct 用 initial_capital — 已修复
3. **BUG-060**（维度1）：update_positions_price() 除零风险 — 已修复
4. **BUG-061**（维度4）：rules vs config 不一致（1.0止损-5%→-7%，3.0阈值30→70分）— 已修复

## 数据一致性验证
- total_assets: 1049454.1 ✅
- market_value: 323771.0 ✅  
- hist_pnl: 15521.1 ✅
- 无幽灵持仓 ✅

## 系统健康度：B+ → 预计A（需1周观察确认BUG-010/012不再回归）
