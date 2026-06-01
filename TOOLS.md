# TOOLS.md - 数据源速查 & 常用命令

## 实时数据（交易日 9:15-15:00）

### 指数行情
```bash
curl -s "https://qt.gtimg.cn/q=sh000001,sz399001,sz399006" | iconv -f gb2312 -t utf-8
```
字段：`v_name`~`v_code`~`v_last_close`~`v_price`~`v_change`...`v_amount`

### 涨跌家数
```bash
curl -sL --max-time 15 -A "Mozilla/5.0" "https://legulegu.com/stockdata/market-activity"
# 从 content="2026-XX-XX 上涨:XXXX 下跌:XXXX..." 提取
```

### 个股实时
```bash
curl -s "https://qt.gtimg.cn/q=sz002245,sh600578" | iconv -f gb2312 -t utf-8
```

## 历史数据（akshare）

### 涨停池
```python
import akshare as ak
df = ak.stock_zt_pool_em(date="20260519")
```

### 个股K线（均线计算）
```python
df = ak.stock_zh_a_hist(symbol="002245", period="daily", start_date="20260501", end_date="20260519")
ma5 = df['收盘'].rolling(5).mean().iloc[-1]
ma10 = df['收盘'].rolling(10).mean().iloc[-1]
```

### 板块涨幅
```python
df = ak.stock_board_industry_name_em()
```

## Python 脚本路径

| 脚本 | 用途 | 调用时机 |
|------|------|---------|
| `scripts/lobster_premarket_engine.py` | 盘前选股引擎 | 07:00 |
| `scripts/lobster_bid_filter_v2.py` | 竞价过滤 | 09:25（依赖 /tmp/lobster_bid_input.json） |
| `scripts/scoring_calculator.py` | 量化打分 | 盘前/收盘复盘 |
| `scripts/lobster_backtest.py` | 简易回测 | 进化任务 |
| `scripts/verify_rules.sh` | 规则一致性校验 | 12:30 |
| `scripts/ima_sync.sh` | IMA 知识库同步 | 各任务完成后 |
| `scripts/cron-tasks/CRON_NEWS_AFTERNOON_TASK.md` | 盘中下午快讯 | 14:00 |
| `scripts/cron-tasks/CRON_NEWS_EVENING_TASK.md` | 晚间要闻 | 20:00 |

## /tmp 中间文件

| 文件 | 写入者 | 读取者 | 生命周期 |
|------|--------|--------|---------|
| `/tmp/lobster_premarket_candidates.json` | premarket_engine | bid_filter, 复盘 | 当日 |
| `/tmp/lobster_bid_input.json` | 盘前任务手动构造 | bid_filter | 当日 |
| `/tmp/lobster_bid_result.json` | bid_filter | 买点监控, 复盘 | 当日 |
| `/tmp/scoring_result_*.json` | scoring_calculator | 复盘 | 当日 |
