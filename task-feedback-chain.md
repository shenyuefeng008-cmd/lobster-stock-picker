# 任务反馈链

## 2026-07-09: 浪潮信息幻影买入 — 根因修复与持仓清理

### 事件摘要
- **时间**: 2026-07-09 09:30:12
- **股票**: 浪潮信息(000977)
- **问题**: 华泰API在开盘瞬间返回昨收价78.17（非实时价），系统误将其视为实时报价，经+0.3%滑点后以78.40买入1300股，金额101,946.50元
- **真相**: 浪潮信息今日收盘涨停@85.99，涨停期间价格从未低于85.99。78.40在今日价格区间内从未出现过

### 根因分析
1. 华泰证券 `getQuote` API 在高开股开盘瞬间（09:30:00-09:30:12）可能返回昨收价而非实时价
2. `fetch_quotes_ht()` 未对返回的 `currentPrice` 做合理性校验
3. 系统未将报价与腾讯行情开盘价做交叉验证

### 修复措施 (v1.24)

#### 1. 持仓清理
- 移除浪潮信息(000977) position 和 trade_log 记录
- 恢复资金 101,946.50 至可用资金
- 审计日志: `trading/capital_audit_20260709_浪潮修正.log`

#### 2. 幻影价防护 (`scripts/lobster_intraday_patrol.py`)
- `fetch_quotes_ht()`: 新增 stale 检测 — 若 `currentPrice ≈ limitUp/1.10`（昨收）且 `pct ≈ 0`，标记为幻影数据降级到 westock
- `fetch_quotes_ht()`: 新增极端值检测 — 价格偏离昨收 >10% 拒绝
- `detect_buypoints()`: 买入前新增腾讯API开盘价交叉验证 — 若报价 < 开盘价 × 95%，拒绝买入

#### 3. 配置 (`lobster-config.json`)
- 新增 `price_guard` 节:
  - `max_deviation_from_close`: 0.10
  - `min_multiplier_of_open`: 0.95
  - `reject_on_stale_price`: true

### 修改文件
- `trading/模拟持仓.json` — 移除浪潮信息持仓
- `scripts/lobster_intraday_patrol.py` — +46行幻影价防护
- `lobster-config.json` — price_guard 配置
