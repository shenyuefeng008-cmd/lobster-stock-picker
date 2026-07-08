# 龙虾超短交易系统 - 交接包 README

**交接日期**: 2026-07-01  
**系统版本**: v2.5  
**打包人**: Yuefeng (市场追踪专家)  
**接收人**: [待填写]

---

## 📦 交接包内容

本交接包包含以下文件（共5个文档 + 1个压缩包）：

### 1. 核心文档（必读）
- **`【交接包】龙虾超短交易系统_2026-07-01.md`** — 系统概述/架构/文件结构/Cron时间表/已知问题/快速开始
- **`快速开始指南_2026-07-01.md`** — 接收人前3天工作清单（熟悉系统→深入代码→实战测试）
- **`系统状态快照_2026-07-01.md`** — 当前资金/持仓/Cron状态/最近修复/快速验证命令

### 2. 部署工具
- **`setup_lobster.sh`** — 一键部署脚本（自动复制文件/初始化配置/检查依赖）
- **`lobster_trading_system_2026-07-01.tar.gz`** — 完整系统压缩包（425KB，包含所有脚本/配置/数据文件）

### 3. 系统文件（压缩包内）
- `scripts/` — 38个Python脚本 + 30个Cron任务指令（MD格式）
- `trading/` — 数据文件（模拟持仓/趋势池/催化日历/Bug日志等）
- `config/` — 系统配置（lobster-config.json）
- `MEMORY.md` — 长期记忆（系统状态/历史教训）
- `AGENTS.md` — 工作区规则
- `SOUL.md` — 分析师人设
- `TOOLS.md` — 工具使用指南

---

## 🚀 快速部署（3种方式）

### 方式1：使用部署脚本（推荐）
```bash
# 1. 解压压缩包
tar -xzf lobster_trading_system_2026-07-01.tar.gz

# 2. 运行部署脚本
bash setup_lobster.sh /path/to/target/workspace

# 3. 验证部署
cd /path/to/target/workspace
bash test_system.sh
```

### 方式2：手动解压（适合高级用户）
```bash
# 1. 解压到目标目录
mkdir -p ~/.qclaw/workspace-lobster
cd ~/.qclaw/workspace-lobster
tar -xzf /path/to/lobster_trading_system_2026-07-01.tar.gz

# 2. 初始化配置
cp config/lobster-config.json.example config/lobster-config.json  # 如有示例文件
# 或手动创建配置文件（参考交接文档）

# 3. 验证Python依赖
pip3 install akshare requests
```

### 方式3：在现有Workspace中集成
```bash
# 1. 复制关键文件到现有Workspace
cp -r scripts/ /path/to/existing/workspace/
cp -r trading/ /path/to/existing/workspace/
cp -r config/ /path/to/existing/workspace/

# 2. 复制根文档
cp MEMORY.md AGENTS.md SOUL.md TOOLS.md /path/to/existing/workspace/

# 3. 配置Cron任务（参考交接文档中的Cron时间表）
```

---

## 📋 接收人检查清单

### 第一天（熟悉系统）
- [ ] 阅读 `【交接包】龙虾超短交易系统_2026-07-01.md`
- [ ] 阅读 `MEMORY.md` 了解系统历史和已知问题
- [ ] 阅读 `AGENTS.md` 了解工作区规则
- [ ] 验证Python环境（Python 3.11+ + akshare + requests）

### 第二天（深入代码）
- [ ] 阅读 `scripts/simulated_trading.py` 了解模拟交易核心
- [ ] 阅读 `scripts/lobster_intraday_patrol.py` 了解盘中巡检逻辑
- [ ] 修复P0问题（参考 `系统状态快照_2026-07-01.md`）

### 第三天（实战测试）
- [ ] 观察完整交易流程（盘前→竞价→盘中→收盘）
- [ ] 验证Cron任务全部启用（20个）
- [ ] 手动运行盘中巡检测试
- [ ] 记录问题到 `memory/2026-MM-DD.md`

---

## 🚨 重要提醒

### 1. 自动交易已启用
- **20个Cron任务**全部启用，会在交易时间自动买卖
- **模拟资金**: 当前约110万（初始100万，+10.34%）
- **⚠️ 接收人需决定是否继续自动交易**，如需暂停，执行：
  ```bash
  openclaw cron list --enabled | grep "龙虾" | awk '{print $1}' | while read id; do
    openclaw cron update $id --enabled false
  done
  ```

### 2. 关键依赖
- **Python 3.11** + akshare + requests
- **腾讯行情接口** (qt.gtimg.cn) — 实时价格
- **新浪财经接口** — 涨跌家数（情绪判断）
- **IMA知识库** — 复盘归档（可选）

### 3. 已知问题（需修复）
详见 `【交接包】龙虾超短交易系统_2026-07-01.md` 中的「已知问题」章节

---

## 📞 联系信息

- **交接人**: Yuefeng (微信/电话：[待填写])
- **紧急联系**: [待填写]

---

## 📂 文件清单

### 文档类（5个）
1. `【交接包】龙虾超短交易系统_2026-07-01.md` — 系统概述（8,763字节）
2. `快速开始指南_2026-07-01.md` — 前3天工作清单（2,540字节）
3. `系统状态快照_2026-07-01.md` — 当前状态（5,913字节）
4. `README.md` — 本文件（入口文档）
5. `setup_lobster.sh` — 部署脚本（3,959字节）

### 数据类（1个）
6. `lobster_trading_system_2026-07-01.tar.gz` — 完整系统压缩包（425KB）

### 压缩包内文件统计
- Python脚本: 38个
- Cron任务指令: 30个（MD格式）
- 数据文件: 12个（JSON/MD格式）
- 配置文件: 2个（JSON格式）
- 文档文件: 6个（MD格式）

---

## ✅ 交接完成确认

接收人完成以下事项后，签署确认：

- [ ] 已阅读所有核心文档（3个）
- [ ] 已成功部署系统（运行 `test_system.sh` 通过）
- [ ] 已验证Cron任务全部启用（20个）
- [ ] 已理解系统架构和核心逻辑
- [ ] 已修复至少1个P0问题
- [ ] 已记录3条改进建议到 `memory/2026-MM-DD.md`

**接收人签名**: ________  
**交接完成日期**: 2026-__-__  
**备注**: 

---

**打包完成时间**: 2026-07-01 17:50:00 (GMT+8)  
**下次更新**: 接收人完成交接后，建议每周更新一次系统状态快照
