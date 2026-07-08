
<p align="center">
  <img src="https://img.shields.io/badge/version-v2.5-blue" alt="version">
  <img src="https://img.shields.io/badge/python-3.11+-green" alt="python">
  <img src="https://img.shields.io/badge/license-MIT-lightgrey" alt="license">
  <img src="https://img.shields.io/badge/market-A股-red" alt="market">
</p>

# 🦞 龙虾超短交易系统

> A 股量化短线交易 Agent — 从盘前选股到竞价买入，从盘中巡检到收盘复盘。

一个基于三维度框架（点·线·面）运行的 Python 量化交易系统，集成多源行情采集、多维评分引擎和模拟持仓管理，由 Cron 任务全天候驱动。

---

## 📖 目录

- [功能概览](#功能概览)
- [交易日时间线](#交易日时间线)
- [快速开始](#快速开始)
- [API 配置指南](#api-配置指南)
- [项目结构](#项目结构)
- [策略框架](#策略框架)
- [License](#license)

---

## 功能概览

| 模块 | 说明 |
|------|------|
| **盘前选股** | 涨停池筛选 → 一进二 / 分歧低吸 / 板块卡位 / 趋势低吸 四维度打分 |
| **竞价交易** | 竞价锚定买入 + 兜底机制，联动情绪档位控制仓位 |
| **盘中巡检** | 每 15 分钟统一买卖点监控，先卖后买，含分时止盈逻辑 |
| **午间复盘** | 半日综述 + 持仓评估 + 下午策略调整 |
| **尾盘专项** | 尾盘信号扫描 + T+0 做T 机会捕捉 |
| **收盘复盘** | 全天收益汇总 + 产业图谱更新 + 趋势池维护 |
| **竞价异动监控** | 同花顺thsdk竞价异动采集，筛选抢筹/高开/试盘/急涨，交叉匹配候选池 |
| **分钟K线分析** | 5分钟K线采集，量价异动检测（量>2倍均量/价破前高），买入信号确认 |

---

## 交易日时间线

```
05:00  晚间要闻采集       ── 隔夜消息面扫描
06:00  催化事件采集       ── 题材/公告/行业催化
07:00  盘前选股           ── 四维度候选池生成
09:00  早盘情绪快检       ── 集合竞价前市场温度
09:20  竞价兜底           ── 锚定买入兜底保护
09:25  竞价选股           ── 竞价信号确认
09:30  竞价自动买入       ── 开盘执行买入
09~16  盘中巡检           ── 每 15min 买卖点监控
11:30  午间复盘           ── 半日总结
14:00  下午快讯           ── 午后动态更新
14:45  尾盘专项           ── 尾盘机会扫描
15:00  产业图谱采集       ── 涨停板块归类
15:05  收盘复盘           ── 全天综合复盘
15:06  趋势池更新         ── 趋势标的重新评估
00:10  每日进化优化       ── 经验沉淀 & 规则进化
```

> 此外还有周末 Bug 修复巡检、产业图谱深度进化等周度任务。

---

## 快速开始

### 环境要求

- Python 3.11+
- macOS / Linux
- Node.js（部分工具链需要）
- Git

### 安装

```bash
# 1. 克隆仓库
git clone https://github.com/shenyuefeng008-cmd/lobster-stock-picker.git
cd lobster-stock-picker

# 2. 安装 Python 依赖
pip install -r requirements.txt

# 3. 安装 akshare（开源金融数据）
pip install akshare

# 4. 配置 API Key（详见下方指南）
cp api_keys.example.env .env
# 编辑 .env 填入你的 API Key
```

### 运行

```bash
# 手动触发盘前选股
python scripts/lobster_premarket_engine.py

# 手动触发盘中巡检
python scripts/lobster_intraday_patrol.py

# 查看模拟持仓
python scripts/view_portfolio.py
```

> 完整自动化运行需要配置 Cron 任务调度（推荐使用 openclaw cron 或系统 crontab）。

---

## API 配置指南

系统依赖多个外部 API，按重要程度分为三级：

### 🔴 必须配置（缺一不可）

#### 1. 华泰证券行情 API — 主数据源

15+ 个脚本依赖，提供实时报价、涨停价、停牌状态。

| 项目 | 说明 |
|------|------|
| **环境变量** | `HT_APIKEY` |
| **获取方式** | [华泰证券开发者平台](https://htsc.zhangle.com/) 注册并申请 API Key |
| **配置位置** | `~/.htsc-skills/config` 或写入 `.env` 文件 |
| **认证方式** | API Key 请求头透传 |

```bash
# 方式一：写入技能配置
mkdir -p ~/.htsc-skills
echo '{"HT_APIKEY": "你的KEY"}' > ~/.htsc-skills/config

# 方式二：写入 .env（推荐）
echo 'HT_APIKEY=你的KEY' >> .env
```

#### 2. 腾讯新闻 API — 舆情采集

盘前选股的新闻催化注入。

| 项目 | 说明 |
|------|------|
| **获取方式** | [news.qq.com/exchange](https://news.qq.com/exchange?scene=appkey) |
| **配置命令** | `tencent-news-cli apikey-set YOUR_KEY` |

```bash
# 安装 CLI 后设置 Key
tencent-news-cli apikey-set 你的KEY
```

---

---

### 🟢 无需配置（免费公开）

| 接口 | 用途 | 调用频率 |
|------|------|---------|
| `qt.gtimg.cn` | 腾讯行情（实时股价） | 15+ 脚本依赖 |
| `web.ifzq.gtimg.cn` | 腾讯 K 线（历史日线） | 趋势池/买点检测 |
| `legulegu.com` | 乐股乐估（涨跌家数） | 情绪分析 |
| `sina.com.cn` | 新浪财经（A股列表） | 降级备用 |
| `push2.eastmoney.com` | 东方财富（涨跌家数备用） | 情绪备用 |

---

### 配置文件快速检查

```bash
# 检查所有 API Key 是否就绪
python scripts/check_api_status.py
```

---

## 项目结构

```
lobster-stock-picker/
├── scripts/               # 核心策略引擎（51 个脚本）
│   ├── lobster_premarket_engine.py   # 盘前选股
│   ├── lobster_intraday_patrol.py    # 盘中巡检
│   ├── lobster_buypoint_detector.py  # 买点检测
│   ├── simulated_trading.py          # 模拟交易
│   ├── lobster_trend_pool_updater.py # 趋势池更新
│   ├── scoring_calculator.py         # 多维评分
│   ├── get_market_sentiment.py       # 市场情绪
│   └── ...
├── config/                # 配置文件
│   ├── lobster-config.json          # 主配置（评分权重/仓位/止损）
│   └── trading_calendar.json        # A股交易日历
├── trading/               # 运行时数据（78 个文件）
│   ├── 模拟持仓.json               # 当前持仓 & 历史 PnL
│   ├── trend_pool.json             # 趋势池（T1~T4 分级）
│   ├── premarket_candidates.json   # 盘前候选池
│   ├── catalyst_db.json            # 催化事件库
│   └── ...
├── reports/               # 每日分析报告
│   ├── 盘前选股_YYYYMMDD.md
│   ├── 午间复盘_YYYYMMDD.md
│   ├── 收盘复盘_YYYYMMDD.md
│   └── ...
├── rules.md               # 策略规则（持续进化）
├── MEMORY.md              # 经验记忆库
├── BUG_LOG.md             # Bug 记录与修复日志
└── .gitignore
```

---

## 策略框架

### 四个选股维度

| 维度 | 策略 | 适用环境 | 核心指标 |
|------|------|---------|---------|
| **1.0 一进二** | 打板接力 | 情绪正常/偏弱 | 竞量比、高开幅度、首板成交额、板块强度 |
| **1.0 分歧低吸** | 连板低吸 | 情绪偏弱/冰点 | 连板高度、低开幅度、成交衰减、均线支撑 |
| **2.0 板块卡位** | 板块龙头识别 | 有主线行情 | 板块涨停数、前排成交额、板块地位、分时 |
| **3.0 趋势低吸** | 趋势回调买入 | 市场正常 | 产业逻辑、均线排列、回踩位置、成交额 |

### 风控体系

| 机制 | 规则 |
|------|------|
| **情绪联动** | 涨家数 <1600 全停一进二，<1900 熔断趋势低吸 |
| **炸板率冻结** | 炸板率 >40% 冻结全天新开仓 |
| **硬止损** | -7% 无条件止损 |
| **时间止损** | 买入后 3 日不创新高止损 |
| **仓位控制** | 冰点 ≤30% → 高潮 ≤10% |

---

## License

MIT License — 详见 [LICENSE](LICENSE) 文件。

---

<p align="center">
  <sub>Built with ❤️ and Python. 交易有风险，代码仅供学习参考。</sub>
</p>
