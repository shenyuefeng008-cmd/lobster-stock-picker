# 盘中巡检 2026-06-23

## 目标
执行龙虾盘中巡检cron任务

## 关键结果
- 情绪：3563涨/1542跌，极度高潮，日内振幅2639
- 仓位上限20%，当前0%
- 买点触发：亨通光电(600487) 趋势低吸回踩MA5(114.19)不破
- 无卖点信号

## Bug修复
- simulated_trading.py `today_str()` NameError → 改为 `datetime.date.today()`
- _is_trading_day() 需要 date 对象非字符串

## IMA同步
- 凭证获取失败，已备份
