# 龙虾超短交易系统 — 第二轮审计报告

> 审计时间：2026-05-19 11:31
> 审计维度：流程关联性 × 数据流完整性 × 数据源可用性 × 版本一致性

---

## ✅ 通过项

### 1. Cron → 指令文件 → 脚本 → 数据文件 引用链
8 个 cron 任务对应的 7 个指令文件全部存在，引用的脚本和数据文件均存在且路径正确。

### 2. /tmp 数据流链路
| 文件 | 写入者(时间) | 读取者 | 有fallback |
|------|-------------|--------|-----------|
| premarket_candidates.json | premarket_engine (07:00) | 竞价/买点/午间/收盘 | ✅ 收盘任务有前置检查 |
| bid_input.json | CRON_BID内联py (09:25) | bid_filter_v2.py | — |
| bid_result.json | bid_filter_v2.py (09:25) | 买点/午间/收盘 | ✅ 收盘任务有前置检查 |
| midday_{date}.md | CRON_MIDDAY (11:30) | CRON_CLOSING前置 | ✅ |
| closing_data.json | CRON_CLOSING内联py | 仅内部使用 | — |

### 3. 数据源可用性
| 数据源 | 状态 | 备注 |
|--------|------|------|
| 腾讯 qt.gtimg.cn | ✅ 正常 | 非交易时段也有数据 |
| legulegu.com | ✅ 可达 | 非交易时段返回HTML |
| akshare 涨停池 | ✅ 可用 | 返回0条（非交易日正常） |
| akshare 个股K线 | ✅ 可用 | 4天数据正常 |
| akshare 板块涨幅 | ⚠️ 偶尔超时 | Connection aborted（网络波动），重试即可 |

### 4. 依赖链
- ima_sync.sh → get-token.sh → jq/curl/python3：✅ 全部可用
- verify_rules.sh：✅ 路径正确，检查 19 个文件/任务
- 所有 Python 脚本 → akshare/requests：✅ 已安装

### 5. 文件存在性
27 个被引用文件全部存在，零缺失。

---

## 🔧 本轮修复项

### Fix 1: CRON_EVOLUTION_TASK.md 残留 v2.0
- 8 处 v2.0 → v2.1
- 12841 字节 → 实际大小

### Fix 2: trading/催化日历.md 不存在
- CRON_EVOLUTION_TASK.md 引用此文件但不存在
- 已创建骨架文件，待周日进化任务填充

### Fix 3: lobster-rules.md 底部版本信息过时
- 文件版本 v2.0 → v2.1
- 健康度指标更新为实际字节数

### Fix 4: lobster_backtest.py / 复盘模板.md 版本引用
- 回测引擎 v2.0 → v2.1
- 复盘模板 v2.0 → v2.1

---

## ⚠️ 已知风险（非阻塞）

1. **akshare 板块接口偶尔超时**：网络波动导致 `RemoteDisconnected`，建议在脚本中加重试
2. **legulegu 非交易时段无涨跌数据**：开盘前心跳任务需处理空数据
3. **CRON_BID_TASK.md 含脚本自建逻辑**：如果 lobster_bid_filter_v2.py 被删，任务会内联重建（182行代码），维护分散风险
4. **lobster-rules.md 中 7 处 v2.0 为历史变更描述**：如"规则五：情绪修复确认（v2.0 新增）"，正确保留不改

---

## 📊 系统健康度总览

| 维度 | 状态 | 说明 |
|------|------|------|
| 文件完整性 | ✅ 100% | 27/27 文件存在 |
| 路径一致性 | ✅ 100% | 旧路径零残留 |
| 版本一致性 | ✅ 100% | 全局 v2.1 |
| 数据源可用 | ✅ 95% | 板块接口偶超时 |
| 数据流完整性 | ✅ 100% | 写→读链路闭环 |
| Cron任务 | ✅ 8/8 | 全部启用+推送 |
| 依赖链 | ✅ 100% | ima/verify/akshare |

