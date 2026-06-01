# 修复报告：时间止损自然日BUG — 2026-06-01 11:08

## BUG描述
粤电力A（000539）在周五05-29买入后，周一06-01被自动止损卖出，触发条件是「持仓3天未涨停」。但实际上只经过1个交易日（周末不算），系统在用自然日而非交易日计算持仓天数。

## 修复范围

### 1. lobster_sellpoint_detector.py
**修复前：** `hold_days = (datetime.date.today() - buy_date).days`（自然日）
**修复后：** `hold_days = count_trading_days(buy_date, datetime.date.today())`（交易日）
- 新增交易日历数据（HOLIDAYS_2026 / ADJUSTED_WORKDAYS_2026）
- 新增 `is_trading_day()` 和 `count_trading_days()` 函数
- v1.1 → v1.2

### 2. simulated_trading.py
- 新增相同的交易日计算工具函数
- 第643行：`sell()` 函数中的 hold_days 改为交易日计算
- 第744行：`partial_sell()` 函数中的 hold_days 改为交易日计算

## 验证结果
```
买入2026-05-29（周五）→ 今天(06-01周一) = 1个交易日 ✅（不触发3日止损）
买入2026-05-27（周三）→ 今天(06-01周一) = 3个交易日 ✅（触发3日止损）
买入2026-05-25（周一）→ 今天(06-01周一) = 5个交易日 ✅（触发5日止损）
```

## 教训
时间止损/持仓天数必须用「交易日」而非「自然日」。A股周末休市，两天自然日可能只差1个交易日。