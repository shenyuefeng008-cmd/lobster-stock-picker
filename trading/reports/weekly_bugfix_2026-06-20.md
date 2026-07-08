# 龙虾周六Bug修复巡检 2026-06-20

## 扫描结果
- 维度1 代码逻辑：3个Bug（3个已修复，0个待人工）
- 维度2 数据一致性：0个Bug（当前数据一致）
- 维度3 Cron任务：0个Bug（21个CRON_MD文件完整）
- 维度4 配置一致性：1个Bug（1个已修复，0个待人工）

## 修复明细
| # | Bug | 维度 | 修复动作 | 验证结果 |
|---|-----|------|---------|---------|
| 1 | sell_partial() 未调用 _update_capital_after_trade()（BUG-010/012反复回归30+次的真正根因） | 维度1 | sell_partial() _save前增加 _update_capital_after_trade(data, actual_price, code) | ✅ 语法验证通过 |
| 2 | sell_partial() position_pct 用 initial_capital 而非 total_assets | 维度1 | 改为 data['capital']['total_assets'] | ✅ 语法验证通过 |
| 3 | update_positions_price() total_pnl_pct 除零风险 | 维度1 | 增加 if p['cost'] else 0 保护 | ✅ 语法验证通过 |
| 4 | rules文档1.0止损写-5%（实际-7%），3.0阈值写30分（实际70分） | 维度4 | 更新rules文档与config一致 | ✅ |

## 重点发现

**BUG-010/012回归根因定位**：从5月28日到6月19日，BUG-010(market_value不一致)和BUG-012(total_assets不一致)共回归30+次。每次巡检都"重新计算修复"但下次又出现。本次定位到根因：`sell_partial()` 函数在保存前没有调用 `_update_capital_after_trade()`，导致部分卖出（止盈减半）后 market_value 和 total_assets 不同步。这是一个结构性修复，应彻底消除该Bug的回归。

## 系统健康度
B+（根因修复后应提升至A，需观察1周确认BUG-010/012不再回归）
