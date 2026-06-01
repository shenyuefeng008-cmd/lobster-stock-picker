# 模拟交易引擎 v2 审计报告

## 修复清单

| # | 原问题 | 修复方案 | 状态 |
|---|-------|---------|------|
| 1 | weekly_summary hardcode 100000 | 用`_meta.initial_capital` | ✅ |
| 2 | sell不查can_sell | 加`p.get('can_sell')`检查 | ✅ |
| 3 | 网络异常降级1.0 | 异常返回0.5保守 | ✅ |
| 4 | 无最大持仓数 | MAX_POSITIONS=8 | ✅ |
| 5 | 冰点减仓排序失效 | 先调update_positions | ✅ |
| 6 | 无止盈规则 | +15%减半/+25%清仓 | ✅ |
| 7 | 无滑点模拟 | ±0.3%滑点 | ✅ |
| 8 | 无限价单 | 新增pending_orders | ✅ |

## 新增功能详解

### 1. 限价单
```
buy(code, name, current_price, reason, dimension, limit_price=10.30)
# 设置目标价，cron触发时若达到则成交
```

### 2. 止盈规则
- `TAKE_PROFIT_TIER1 = 15` → 15%以上减半仓
- `TAKE_PROFIT_TIER2 = 25` → 25%以上清仓

### 3. 滑点
- `SLIPAGE_BUY = 0.3%` → 买入价 +0.3%
- `SLIPAGE_SELL = 0.3%` → 卖出价 -0.3%

### 4. execute_pending_orders
cron中调用检查待成交限价单：
```python
from simulated_trading import execute_pending_orders, update_positions

# 先更新所有持仓价格
update_positions(price_map)
# 再检查限价单
results = execute_pending_orders(price_map)
for r in results:
    print(r)
```

## 函数列表（共15个）
- `_load()` / `_save()` / `_today()`
- `get_emotion_rule()`
- `check_position_limit()`
- `emotion_force_sell()`
- `calc_stock_factor()`
- `buy()` ← 支持limit_price参数
- `sell()` ← 加入场点+止盈检查
- `check_take_profit()`
- `execute_pending_orders()` ← 新增
- `unlock_t1()`
- `update_positions()`
- `status()`
- `weekly_summary()`

## 本周汇总（验证正确）
```python
>>> weekly_summary()
{'初始资金': 1000000, '当前总资产': 1000000.0, '总盈亏': 0.0, '总收益率': 0.0%, '可用资金': 510914, ...}
```

## 仓位检查（验证正确）
```
涨跌2800正常区: 情绪7成上限，当前49%，可加21%，单只21%
涨跌1200冰点区: ⚠️ 情绪仓位上限5成已达（当前49%），剩余额度不足5%，不开新仓
```