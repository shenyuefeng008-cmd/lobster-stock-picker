# 龙虾超短交易系统 — 全流程审计报告

> 审计时间：2026-05-19 11:17
> 审计范围：文件完整性 × 路径一致性 × 脚本逻辑 × Cron任务 × 专家身份配置

---

## 🔴 P0 — 必须立即修复（否则明天任务会跑飞）

### 1. Python 脚本中路径错误（3处）

| 文件 | 行号 | 问题 | 修复 |
|------|------|------|------|
| `lobster_premarket_engine.py` | L15 | CONFIG_PATH 引用 `memory/lobster-config.json`，实际在根目录 | → 改为 `parent.parent / 'lobster-config.json'` |
| `lobster_premarket_engine.py` | L120 | `memory/趋势容量池.md`，实际在 `trading/` | → 改为 `trading/趋势容量池.md` |
| `lobster_bid_filter_v2.py` | L121 | `memory/关注股.md`，实际在 `trading/` | → 改为 `trading/关注股.md` |

**影响**：07:00 盘前选股引擎读取不到配置文件和趋势池，会报错或输出空结果。

### 2. verify_rules.sh 硬编码旧路径

```bash
WORKSPACE="$HOME/.qclaw/workspace-agent-18d6c2a1"
```
**影响**：12:30 规则校验脚本指向旧工作区，校验结果无意义。

### 3. Cron任务指令文件中残留旧路径（15处）

| 文件 | 残留数 |
|------|--------|
| CRON_MIDDAY_TASK.md | 5处 |
| CRON_CLOSING_TASK.md | 4处 |
| CRON_DAILY_EVOLUTION_TASK.md | 4处 |
| CRON_BUYPOINT_TASK.md | 1处（前置校验） |
| CRON_PREMARKET_TASK.md | 0处 ✅ |
| CRON_BID_TASK.md | 0处 ✅ |

**影响**：午间复盘、收盘复盘、每日进化任务执行时，前置校验和IMA同步会指向旧路径。

---

## 🟡 P1 — 建议尽快修复

### 4. trading-state.json 情绪数据过期

```json
"lastSentiment": {"date": "20260514", "upDown": 1010, "period": "极度冰点"}
```
数据停在 5月14日，距今已5个交易日。明天盘前选股读到这个数据会误判情绪。

**修复**：运行一次实时情绪查询更新，或在每日进化任务中自动刷新。

### 5. heartbeat-rules-full.md 内容空洞

文件只有 57 行，标题写"完整版"，实际内容和精简版 HEARTBEAT.md 几乎一致，缺少：
- 收盘复盘检查项（CRON_CLOSING_TASK.md 引用此文件）
- 详细告警条件表
- P1买点具体信号条件

**影响**：午间/收盘任务读到"详细规则见 heartbeat-rules-full.md"后会发现没有详细内容。

### 6. lobster-rules.md 版本号矛盾

- 标题写 **v2.1**
- 正文多处写 "v2.0 重大升级"
- 文件大小指标写的 12841 字节，实际 13632 字节

**修复**：统一版本号为 v2.1，更新文件大小指标。

### 7. Cron 任务缺少 timeoutSeconds

只有盘前/竞价/买点/午间/收盘设了 300s，但：
- 每日进化（00:00）无 timeout → 可能无限运行
- 规则校验（12:30）无 timeout
- 买点监控（每小时）300s 是否够用待验证

---

## 🟢 P2 — 建议优化（不影响核心流程）

### 8. 趋势容量池.md 当前为空

```
grep -c "^[0-9]\." trading/趋势容量池.md → 0
```
3.0 维度选股依赖此文件，空池意味着 3.0 维度永远不会选出标的。

**建议**：从交接文件中的示例恢复，或等盘前引擎运行后自动填充。

### 9. 重复文件：trading/心跳规则.md vs heartbeat-rules-full.md

两个文件功能重叠：
- `trading/心跳规则.md`（289行）— 更详细
- `trading/heartbeat-rules-full.md`（57行）— 几乎空壳

**建议**：合并为一个文件，删除空壳。

### 10. Cron 任务无推送渠道

当前所有 8 个任务 delivery=none（本地静默执行）。如果不在 webchat 界面查看，结果不可见。

**建议**：至少盘前选股、竞价选股、收盘复盘推送到元宝或微信。

### 11. /tmp 依赖风险

所有 Python 脚本读写 `/tmp/lobster_*.json` 和 `/tmp/lobster_*.md`。系统重启后丢失。

**影响**：如果竞价任务依赖盘前写入 /tmp 的 JSON，跨日会丢失数据。
**当前设计**：盘中任务（竞价/买点/午间/收盘）在同一天执行，实际影响不大。但收盘复盘读盘前 JSON 如果跨日可能有问题。

---

## 🦞 专家身份审计

### ✅ 配置正确的
- IDENTITY.md：名称"市场追踪专家" + 头像 ✅
- SOUL.md：人格清晰（快、结论先给、数据跟上）✅
- AGENTS.md：三维度框架 + 红线 + Session Startup 流程 ✅
- MEMORY.md：长期记忆 + 交接记录 ✅
- neodata skill：金融数据搜索能力 ✅

### ⚠️ 建议调整
1. **SOUL.md 过于简短**（仅3条），缺少"语气示例"——建议补充2-3个回复模板，让LLM更好模仿
2. **USER.md 空白**——不知道用户是谁，无法个性化（如持仓偏好、风险承受能力）
3. **TOOLS.md 空白**——建议写入数据源速查表和常用curl命令

---

## 📋 修复优先级总结

| 优先级 | 项 | 工作量 |
|--------|------|--------|
| 🔴 P0 | Python脚本3处路径错误 | 5分钟 |
| 🔴 P0 | verify_rules.sh 旧路径 | 1分钟 |
| 🔴 P0 | Cron任务指令文件15处旧路径 | 10分钟 |
| 🟡 P1 | trading-state.json 过期 | 5分钟 |
| 🟡 P1 | heartbeat-rules-full.md 内容空洞 | 需补充内容 |
| 🟡 P1 | lobster-rules.md 版本号矛盾 | 2分钟 |
| 🟡 P1 | timeoutSeconds 缺失 | 3分钟 |
| 🟢 P2 | 趋势容量池为空 | 待数据 |
| 🟢 P2 | 重复文件清理 | 2分钟 |
| 🟢 P2 | 推送渠道配置 | 10分钟 |

**预计总修复时间**：~30分钟（不含内容补充）

