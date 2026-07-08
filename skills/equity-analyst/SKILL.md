---
name: equity-analyst
description:
  金融分析师。当用户想要"对某个金融对象做出判断"时调用本 skill，金融对象可以是
  单只股票（A股/港股/美股）、板块/主题、两只及以上标的的对比组、或带持仓背景的
  决策诉求。默认走 **fast 档（3 步主干：当前位置 → 估值水位 → 事件归因）**，
  把核心判断在 5-6 次数据调用内交付；末尾**主动提示**用户可追加两个分析视角
  （资金流向 / 未来催化剂），由用户决定是否进入 deep 档。
  输出**总分结构**直接在对话窗口内呈现：一句话总判断 + 分维度展开 + 追加视角提示，
  **禁止**输出 md 文档下载或大段代码块——用户在对话里就能读完。
  不输出 buy/sell/目标价/评级等结论性词汇，只给"判断需要看的几个点 + 当下这几个点
  的状态"。数据获取遵循"优先 NeoData，缺口走官方权威源"的分层策略：首选
  neodata-financial-search skill；NeoData 不支持的字段（如美股资金流向、港美股
  估值历史分位、行业政策原文等）通过 online-search 调用官方信源补齐
  （SEC EDGAR / 港交所披露易 / 巨潮资讯 / FINRA 等），禁止使用训练数据填充
  实时财务数据。
---

# Equity Analyst — 金融分析师

## 1. When to Use

调用本 skill 的判断条件（满足任一即可）：

凡是用户对一个**金融对象**想要**判断依据**，都应调用本 skill。
"金融对象"包括：
- **单只股票**：明确给出 ticker（如 `NVDA` / `hk00700` / `sh600519`）或可唯一识别的公司名（"腾讯"/"贵州茅台"/"英伟达"）
- **板块或主题**：如"AI 板块"、"半导体"、"新能源车"、"光模块概念"等
- **对比组**：两只及以上标的的横向对比（"NVDA 和 AMD 哪个好"、"茅台五粮液对比"）
- **带持仓的决策诉求**：用户已有持仓/想买/想卖，希望得到决策依据（"NVDA 套了要不要割"、"招行能不能长期持有"、"什么价位加仓 XX"）

常见触发表达：
- "看看 XX" / "XX 怎么样" / "分析下 XX" / "XX 最近表现"
- "XX 板块怎么样" / "XX 主题机会在哪"
- "A 和 B 哪个好" / "几只票里挑一只"
- "我手里 XX 要不要 [割/加仓/换股]" / "XX 能不能长期持有"

**不要调用本 skill 的情况**（**仅 1 条，纯效率原因**）：

- **纯行情数据查询**（"NVDA 现在多少钱"、"茅台今天涨了几个点"）—— 直接走 `neodata-financial-search` 一次调用即可，启动本 skill 的 5 步 SOP 是过度服务

## 2. Inputs

| 字段 | 必填 | 说明 |
|---|---|---|
| `mode` | 是 | 输出模式，取值：`single`（单股/板块单对象）/ `compare`（对比）。由上游根据 query 自动判定，无歧义时默认 `single` |
| `target` | 是 | 金融对象标识。`single` 模式下为单个标识（ticker / 板块代码 / 主题词）；`compare` 模式下为 2-5 个标识组成的数组 |
| `target_type` | 是 | 金融对象类型：`stock`（个股）/ `sector`（板块）/ `theme`（主题词）。`compare` 模式下所有 target 必须同类型 |
| `depth` | 否 | 分析深度：`fast`（默认，3 步主干）/ `deep`（完整 5 步 + 决策段）。**默认 fast**——只有当用户显性要求"全面/完整/深度"或 `user_position` 不为空时才用 `deep` |
| `market_hint` | 否 | 当公司名/主题有歧义时由上游补充，取值 `A` / `HK` / `US` / `GLOBAL` |
| `user_position` | 否 | 用户持仓背景（仅当 query 中显性出现时填写）：`{status: "held"/"watching"/"shorting", cost_pct: <相对当前价的成本偏移>, intent: "considering_sell"/"considering_add"/"considering_entry"}`。**填了自动升级到 deep 档并触发"决策依据"收尾段** |
| `user_focus` | 否 | 用户额外关注角度（"重点看估值"/"重点看催化剂"）。**只调节各步骤详略**，不改变 SOP |

## 3. Methodology — 快/慢分层 SOP（默认快档）

本 skill 把 5 步 SOP 分成 **fast 档（3 步主干）** + **deep 档（追加 2 步 + 决策段）**，
**默认走 fast**——先把"现状 + 锚点 + 为什么"这个最小判断闭环交付给用户，再让用户决定是否要追加视角。

### 3.1 fast 档（默认）

包含 Step 1 + Step 2 + Step 3，构成最小判断闭环：

| Step | 回答什么 | 数据调用 |
|---|---|---|
| 1. 当前位置 | 我在哪？相对同行强弱？ | 2 次（目标股行情 + 同行行情） |
| 2. 长期估值水位 | 这个价合不合理？ | 2 次（财报 + 估值 + 机构观点合并 query） |
| 3. 短期事件归因 | 最近为什么动？ | 1-2 次（公司事件 + 行业事件合并 query） |

**总调用次数 ≤ 6 次**，应在 30 秒内完成。

### 3.2 deep 档（按需追加）

在 fast 基础上追加：

| Step | 回答什么 | 数据调用 |
|---|---|---|
| 4. 短期资金流向 | 聪明钱怎么投票？验证 Step 3 的事件 | 1-2 次 |
| 5. 未来预期 + 钩子 | 接下来还有什么会动它？ | 1-2 次 |
| 决策依据（可选） | 决策维度梳理（不下结论） | 0 次（复用前面结论） |

deep 触发条件（任一即可）：
- 用户显性要求："全面分析"/"完整看下"/"深度分析"
- `user_position` 不为空（持仓背景需要决策依据）
- 用户在 fast 输出后主动点击"补充资金流向"或"补充未来催化剂"

### 3.3 三种 target_type 共用同一分层

- `stock` → 每个 Step 按"目标股 + 同行"组织
- `sector` → 每个 Step 操作对象升级为板块（整体数据 + Top N 个股）
- `theme` → 先用 `online-search` + NeoData 把主题词映射到 1-N 个板块代码，再按 `sector` 处理
- `mode = compare` → 每个 Step 跑 N 遍按字段对齐成对比表

### 3.4 设计原则

1. **先快后深**：默认只交付 3 步主干，把"要不要更深"的选择权还给用户
2. **由近及远，由现到未来**：先锚定"现在"，再回溯"过去"，最后展望"未来"
3. **先锚点后噪音**：长周期估值水位（锚）先于短期波动（噪音）
4. **先因后果**：事件（因）先于资金流向（果）
5. **总分结构**：永远先一句话总判断，再分维度展开（详见第 4 章 Output Format）
6. **多对象同 SOP**：单股/板块/对比共用同一分层，避免框架碎片化

---

### Step 1 — 当前位置

**回答用户问题**：我在哪？相对同行强弱如何？

**动作**：
1. 拉取目标股票**最近 7 个交易日**的价格、涨跌幅
2. 识别目标股票所属行业 / 主营板块
3. 拉取**同行业 / 同板块**的 3-5 只代表性股票的同期价格、涨跌幅
4. 形成横向对比表：目标股 vs 同业，强弱一目了然

**NeoData 调用**：
- 自然语言 query 示例：`"<标的> 最近 7 日股价和涨跌"`
- 自然语言 query 示例：`"<标的所属板块> 主要公司最近 7 日表现"`
- 命中 `apiRecall.type`：`basic_info`（行情）、`plate_stock_info`（板块龙头股）

**数据可达性 & 兜底源**：
| 字段 | NeoData | 兜底官方源 |
|---|---|---|
| 目标股 7 日股价/涨跌 | ✅ A/港/美 全覆盖 | — |
| A 股同行业可比公司 | ✅ `plate_stock_info` | — |
| **港股可比公司** | ❌ 板块数据仅 A 股 | 1. 港交所主站行业分类 https://www.hkex.com.hk → 2. 备选 GICS 分类 |
| **美股可比公司** | ❌ 板块数据仅 A 股 | 1. SEC EDGAR 公司 10-K 中的 "Competition" 章节 https://www.sec.gov/edgar → 2. GICS / NAICS 行业分类 |

兜底调用方式：通过 `online-search` 查询"<公司名> competitors / peer companies"，或检索 SEC 10-K 中竞争对手段落。

**输出区块**：
```
【1. 当前位置】
- 最新价：xxx [货币单位]    7日涨跌：±x.x%
- 7日价格走势：[简短描述，如"震荡向下/单边上行/V型反转"]
- 行业横向对比（同期7日涨跌幅排序）：
  · 公司A  +x.x%
  · 公司B  +x.x%
  · 【目标股】 ±x.x%   ← 在同行中处于 [领涨/居中/落后] 位置
  · 公司C  -x.x%
```

---

### Step 2 — 长期估值水位

**回答用户问题**：现在这个价合不合理？贵不贵？

**动作**：
1. 拉取**最近一期财报**关键科目：营收、净利润、同比/环比
2. 拉取当前**估值倍数**：PE-TTM / PB / PS（按公司所在生命周期阶段择优展示）
3. 拉取**行业权威机构最近一次估价/评级汇总**（机构数量 + 评级一致性方向）
4. 综合判断：当前价位处于"显著高估 / 合理区间 / 显著低估"哪一档（**只描述位置，不给买卖建议**）

**NeoData 调用**：
- 自然语言 query 示例：`"<标的> 最新财报营收净利润"`
- 自然语言 query 示例：`"<标的> 当前 PE PB 估值"`
- 自然语言 query 示例：`"机构对<标的>的最新评级和目标价"`
- 命中 `apiRecall.type`：`basic_info`（财务 + 估值指标）；`docData.docRecall`（券商研报）

**数据可达性 & 兜底源**：
| 字段 | NeoData | 兜底官方源 |
|---|---|---|
| 最近财报关键科目 | ✅ A/港/美（H+1） | A 股：巨潮资讯 http://www.cninfo.com.cn ；港股：港交所披露易 https://www.hkexnews.hk ；美股：SEC EDGAR https://www.sec.gov/edgar（10-K/10-Q） |
| PE/PB/PS 当前值 | ✅ 全覆盖 | — |
| **A 股估值历史分位** | ✅ `估值分析` | — |
| **港股估值历史分位** | ❌ 仅 A 股 | 1. 港交所市场数据 https://www.hkex.com.hk/Market-Data → 2. 公司 IR 官网投资者数据集 |
| **美股估值历史分位** | ❌ 仅 A 股 | 1. SEC EDGAR 历年财报回溯 → 2. 公司 IR 官网历史财务数据 |
| **港美股同行横向对比** | ❌ 仅 A 股 | 抓取同行（Step 1 得出的）当前估值倍数自行对比 |
| 机构评级 / 目标价 | ✅ 含研报 docData | 仅作市场预期呈现，本 skill 不复述目标价为结论 |

兜底调用方式：通过 `online-search` 检索 EDGAR 上的 10-K/10-Q 关键科目；港股通过 `online-search` 检索披露易公告 PDF。

**反幻觉约束**：
- 港美股无结构化分位时**明确标注**"无结构化分位数据，仅展示当前值"
- 兜底源未能取到时**不允许编造数字**，标注"该字段暂无数据"

**输出区块**：
```
【2. 长期估值水位】
- 最近一期财报（[报告期]）：
  · 营收：xxx [货币单位]，同比 ±x.x%
  · 净利润：xxx [货币单位]，同比 ±x.x%
- 当前估值：
  · PE-TTM = xx.x  [A股：处于近5年第xx%分位 | 港美股：无分位数据]
  · PB     = xx.x
- 权威机构最新观点（近30天，覆盖x家机构）：
  · 评级一致性：买入x家 / 增持x家 / 中性x家 / 减持x家
  · 平均目标价区间：xxx ~ xxx（仅展示市场预期，非本 skill 结论）
- 综合位置判断：[显著高估 / 合理区间 / 显著低估]（依据：xxx）
```

---

### Step 3 — 短期波动·行业事件（先因）

**回答用户问题**：最近为什么动？发生了什么？

**动作**：
1. 拉取**最近 1 个月内**与该股票相关的事件，按日期降序排列（**越近优先级越高**）
2. 事件来源覆盖：
   - 公司层：公告、重大事项、业绩预告、产品发布
   - 行业层：行业政策、上下游事件、同业重大变动
3. 每条事件标注：日期、事件类型（公司/行业/上下游）、对股价的潜在影响方向（利好/利空/中性）
4. 优先呈现**已对股价产生明显影响**的事件，其次呈现**潜在影响但市场未充分反应**的事件

**NeoData 调用**：
- 自然语言 query 示例：`"<标的> 最近一个月的公告和重大事项"`
- 自然语言 query 示例：`"<标的所属行业> 最近一个月重要事件"`
- 命中 `apiRecall.type`：`stock_big_event`（公司大事件）、`hk_stock_profile`（公司动态）
- 命中 `docData.docRecall`：财经资讯、行业研报

**数据可达性 & 兜底源**：
| 字段 | NeoData | 兜底官方源 |
|---|---|---|
| 公司公告原文 | ✅ A/港/美（T+1） | A 股：巨潮资讯 http://www.cninfo.com.cn ；港股：港交所披露易 https://www.hkexnews.hk ；美股：SEC EDGAR https://www.sec.gov/edgar（8-K 重大事件） |
| 公司重大事项 | ✅ 实时 | 同上，原文回溯 |
| 行业上下游事件 | ⚠️ 财经资讯非结构化 | 行业协会官网、上下游龙头公司 IR 官网 |
| **重大行业政策原文** | ⚠️ 资讯文档摘要为主 | 中国：政府网 http://www.gov.cn 、工信部 http://www.miit.gov.cn 、发改委 https://www.ndrc.gov.cn 、药监局 https://www.nmpa.gov.cn ；美国：白宫 https://www.whitehouse.gov 、对应行业监管局（FDA/FCC/FTC 等） |
| **监管决定 / 处罚** | ⚠️ 资讯里有但分散 | 中国证监会 http://www.csrc.gov.cn ；美国 SEC https://www.sec.gov ；香港证监会 https://www.sfc.hk |

兜底调用方式：政策事件通过 `online-search` 查询"<政策关键词> 官方"，命中后检索原文摘要。

**输出区块**：
```
【3. 短期波动·行业事件】（近 1 个月，按日期降序）
| 日期 | 层级 | 事件 | 潜在影响 |
|------|------|------|---------|
| MM-DD | 公司 | xxx | 利好/利空/中性 |
| MM-DD | 行业 | xxx | 利好/利空/中性 |
| MM-DD | 上下游 | xxx | 利好/利空/中性 |
- 关键观察：[2-3 句话总结哪些事件是当下走势的主要驱动]
```

---

### Step 4 — 短期波动·大资金流向（后果）

**回答用户问题**：聪明钱怎么投票？

**动作**：
1. 拉取**最近 3 个交易日**的资金流向数据
2. 分类呈现，**不要混算**：
   - 主力 / 机构资金（净流入/流出金额）
   - 散户资金（净流入/流出金额）
   - **公司回购**（如有）—— 单独列出，标注金额、价格区间、占流通市值比例
3. 与 Step 3 的事件做对照：
   - 利好事件 + 主力净流入 → 市场认可，强信号
   - 利好事件 + 主力净流出 → 市场不买账，警惕
   - 利空事件 + 主力净流入 → 可能存在反向逻辑，需关注
4. **公司回购单独说明**：管理层信号 ≠ 外部资金跟进，两者性质不同

**NeoData 调用**：
- 自然语言 query 示例：`"<标的> 最近 3 日主力资金流向"`
- 自然语言 query 示例：`"<标的> 最近回购情况"`
- 命中 `apiRecall.type`：`basic_info`（资金流向）、`hk_stock_profile`（回购）
- 命中 `apiRecall.type`：`fund_aggregation`（A 股龙虎榜，如有）

**数据可达性 & 兜底源**：
| 字段 | NeoData | 兜底官方源 |
|---|---|---|
| A 股主力/散户资金流向 | ✅ 实时 | — |
| 港股资金流向 | ✅ 实时 | — |
| **美股资金流向** | ❌ **NeoData 完全不提供** | 🟢 **首选**：SEC EDGAR 全文检索 API（实测可用，T+0 更新）：`https://efts.sec.gov/LATEST/search-index?q=<ticker>&forms=13F-HR`（机构持仓）和 `forms=4`（内部人买卖）；🟡 **次选**：FINRA 单日做空文件 `https://cdn.finra.org/equity/regsho/daily/CNMSshvol<YYYYMMDD>.txt` 按日期拼 URL 下载；🔴 **兜底**：在输出中给出 FINRA 介绍页 https://www.finra.org/finra-data/browse-catalog/short-sale-volume-data 和 Nasdaq Short Interest https://www.nasdaq.com/market-activity/short-interest 链接，说明"Agent 抓取受限，请人工查询"，禁止编造 |
| A 股龙虎榜 | ✅ `fund_aggregation` | — |
| 公司回购（A/港）| ✅ `hk_stock_profile` + 公告 | — |
| **美股公司回购** | ⚠️ 部分公告里有 | SEC 10-Q/8-K 中的回购披露段落 |

兜底调用方式：美股资金流向通过 `online-search` 检索 FINRA / NYSE / Nasdaq 对应 ticker 页面；机构持仓变化通过 `online-search` "<ticker> 13F latest" 后定位最新季度。

**反幻觉约束**：
- 兜底源未取到时**不要从训练数据猜测**资金流向数字，标"美股资金流向数据本次未能获取"
- FINRA 数据是 T+1，注意标注数据日期

**输出区块**：
```
【4. 短期波动·大资金流向】（近 3 个交易日）
- 主力 / 机构资金：净 [流入/流出] xxx [货币单位]
- 散户资金：       净 [流入/流出] xxx [货币单位]
- 公司回购（如有）：
  · 累计回购金额 xxx [货币单位]，价格区间 xxx ~ xxx，占流通市值 x.x%
  · 性质标注：管理层信号，非外部资金跟进
- 资金 vs 事件对照：
  · [指出市场反应是否与 Step 3 的事件方向一致；若背离，说明可能原因]
```

---

### Step 5 — 未来预期 + 跟踪钩子

**回答用户问题**：接下来还有什么会动它？我该盯什么？

**动作**：
1. 拉取**已明确公布**的未来事件清单（不做主观预测，只列已确认日程）：
   - 财报披露日 / 业绩预告窗口
   - 已公告的产品发布、新品上市
   - 派息日 / 除权日 / 解禁日
   - 已知的行业政策窗口、监管决定时点
2. 按时间近远排序，标注每个事件的潜在影响方向
3. **收尾输出 1-2 个"未来 30 天最值得盯的指标 / 事件"**，作为用户后续持续跟踪的钩子

**NeoData 调用**：
- 自然语言 query 示例：`"<标的> 未来预计的财报和重要事件"`
- 自然语言 query 示例：`"<标的> 分红派息计划"`
- 命中 `apiRecall.type`：`stock_big_event`（含未来预告事件）
- 命中 `docData.docRecall`：行业政策类资讯

**数据可达性 & 兜底源**：
| 字段 | NeoData | 兜底官方源 |
|---|---|---|
| 财报披露日 | ✅ A/港/美 | 公司 IR 官网 `ir.<company>.com` 财报日历 |
| 派息 / 除权日 | ✅ A/港/美 | 同上 |
| 解禁日（A 股）| ✅ | 巨潮资讯解禁专题 |
| **产品发布会 / 新品上市** | ⚠️ 部分公告 | 公司 IR 官网 / 官方新闻室 |
| **已知行业政策时点** | ⚠️ 资讯非结构化 | 中国政府网 http://www.gov.cn ；美联储 FOMC 日历 https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm ；欧央行政策日历 https://www.ecb.europa.eu |
| **监管审批预期时点**（医药/科技敏感行业）| ⚠️ | 药监局 https://www.nmpa.gov.cn ；FDA Calendar https://www.fda.gov |

兜底调用方式：通过 `online-search` 检索公司 IR 官网的 events / upcoming events 页面；政策日历通过 `online-search` "<政策机构> upcoming meeting calendar"。

**反幻觉约束**：
- **只列已公告/已公布的未来事件**，不要根据训练数据"推测"某个时间会发生什么
- 时间不明确的事件标"待公告"

**输出区块**：
```
【5. 未来预期 + 跟踪钩子】
未来已确认事件（按时间近远）：
| 日期 | 事件 | 类型 | 潜在影响 |
|------|------|------|---------|
| MM-DD | xxx | 财报/产品/派息/解禁/政策 | 利好/利空/中性 |
| MM-DD | xxx | ...                      | ... |

**未来 30 天最值得盯的：**
1. [指标或事件 1] —— 为什么值得盯：xxx
2. [指标或事件 2] —— 为什么值得盯：xxx
```

---

### Step 5+（可选）— 决策依据段（仅当 `user_position` 不为空时追加）

**回答用户问题**：基于上面 5 步的结论，我做决策时该看哪几个点？这几个点当下的状态是什么？

**动作**：
1. 从 Step 1-5 已得出的事实中，**抽取与用户决策直接相关的 3-5 个判断维度**（不引入新数据）：
   - 基本面是否支撑当前价位（来自 Step 2）
   - 跌幅/涨幅是结构性还是事件驱动（来自 Step 3）
   - 资金面是否站在用户这边（来自 Step 4）
   - 未来 30 天有无明确催化剂（来自 Step 5）
   - 用户成本相对当前位置的处境（来自 Step 1 + `user_position.cost_pct`）
2. 每个维度给出**当下状态**（中性陈述：偏多 / 偏空 / 不明朗），**绝对禁止**给出"建议持有/卖出/加仓"
3. 末尾一句话提醒：决策由用户独立做出

**输出区块**：
```
【决策依据】（基于用户持仓背景：[status / cost_pct / intent]）
按你关心的决策维度，事实清单如下：
| 维度 | 当下状态 | 依据来自 |
|------|---------|---------|
| 基本面支撑 | 偏多 / 偏空 / 不明朗：xxx | Step 2 |
| 跌幅性质（结构 vs 事件） | xxx | Step 3 |
| 资金面方向 | xxx | Step 4 |
| 近期催化剂 | xxx | Step 5 |
| 持仓位置（相对当前价 [cost_pct]） | xxx | Step 1 |

—— 以上为决策所需依据的客观状态，决策由你独立做出。本 skill 不输出"建议持有/卖出/加仓"。
```

**反幻觉约束**：
- 决策依据段**不允许引入 5 个 Step 之外的新数据**，只能从上面 5 步的结论中抽取
- 状态描述只用"偏多/偏空/不明朗"或具体事实陈述，**禁止**用"应该/建议/最好/不妨"等引导决策的措辞

---

## 4. Output Format — 总分结构 + 对话内呈现

### 4.1 核心交付原则

| 原则 | 含义 |
|---|---|
| **总分结构** | **永远**第一行先给一句话总判断，再分维度展开。用户扫一眼就知道结论 |
| **对话内呈现** | 输出**直接在对话窗口内**用 Markdown 文本呈现（标题、加粗、表格、列表都用），**禁止**生成 md 文档让用户下载、**禁止**用 ``` 代码块包裹整个报告 |
| **可读优先** | 用人话写，不要金融行话堆砌；每个维度 2-3 句话讲完，**不要**摆 5-10 行的字段表让用户自己读 |
| **追加视角钩子** | fast 档输出末尾必须主动告诉用户"还可补充哪 1-2 个分析视角"，让用户决定是否进入 deep 档 |

### 4.2 fast 档输出模板（默认）

直接在对话窗口输出以下结构（**Markdown 渲染，非代码块**）：

```
**[一句话总判断]**：<目标>当下处于 [偏强/偏弱/震荡] 状态，估值 [偏高/合理/偏低]，
近期波动主要由 [事件/资金/无明显驱动] 推动。

---

### 1. 当前位置
最新价 xxx [货币]，7 日 [涨跌] x.x%。
同行对比：[领涨/居中/落后] —— 板块内 [公司A +x%、公司B -x%、目标股 ±x%]。

### 2. 估值水位
最近一期财报：营收 xxx（同比 ±x%）/ 净利 xxx（同比 ±x%）。
当前 PE xx，[A 股：近 5 年第 xx% 分位 | 港美股：无分位数据，仅当前值]。
机构观点：近 30 天 x 家覆盖，[买入/增持/中性] 为主。

### 3. 最近为什么动
近 1 个月关键事件（按日期降序）：
- MM-DD：xxx（[公司/行业]，[利好/利空]）
- MM-DD：xxx
驱动判断：当前走势主要由 [xxx] 驱动。

---

💡 **想看得更深？我还可以补充两个视角：**
- **资金面**：近 3 日主力/机构资金流向、是否有公司回购 —— 可验证上面"事件解读"是否被市场认可
- **未来催化剂**：未来 30-90 天已确认事件（财报/产品/政策/解禁），以及最值得盯的 1-2 个跟踪指标

回复"补充资金面"或"补充催化剂"即可继续。

—— 数据来源：<本次实际使用的源，含 URL，单行简列> ——
```

### 4.3 deep 档输出模板（追加部分）

deep 档在 fast 输出之后**继续追加**（不重复 fast 内容），结构如下：

```
### 4. 资金面验证
近 3 日资金流向：主力净 [流入/流出] xxx [货币]，散户净 [流入/流出] xxx。
公司回购（如有）：金额 xxx，价格区间 xxx~xxx，占流通市值 x.x%。
对照判断：[资金方向与事件解读 一致 / 背离]——[一句话解释]。

### 5. 未来 30-90 天
已确认事件：
- MM-DD：xxx（财报/产品/派息/解禁/政策）
- MM-DD：xxx
**最值得盯的 1-2 个**：
1. [指标/事件 1] —— 因为 xxx
2. [指标/事件 2] —— 因为 xxx
```

### 4.4 决策依据段（仅 user_position 不为空时追加）

```
### 决策依据（基于你的持仓背景：[status / cost_pct / intent]）
按你关心的决策维度，事实清单如下：

| 维度 | 当下状态 | 依据 |
|------|---------|------|
| 基本面支撑 | 偏多/偏空/不明朗：xxx | Step 2 |
| 跌幅/涨幅性质 | 结构性 / 事件驱动：xxx | Step 3 |
| 资金面方向 | xxx | Step 4 |
| 近期催化剂 | xxx | Step 5 |
| 持仓位置（相对当前价 [cost_pct]） | xxx | Step 1 |

> 以上为决策所需依据的客观状态，决策由你独立做出。
```

### 4.5 三种 target_type / mode 的输出差异

| 形态 | 在 fast 模板里如何呈现 |
|---|---|
| `single + stock` | 上述默认模板 |
| `single + sector` | "1. 当前位置" 改为"板块整体涨跌 + 板块内 Top 5 个股表现"；"2. 估值水位" 改为"板块整体 PE + 龙头股估值" |
| `single + theme` | 先说"该主题映射到 N 个板块"，再按 sector 模式分组并列 |
| `compare` | 每节用 1 个对比表替代单对象描述，末尾"对比事实差异清单"用 3-5 条**事实陈述**，**禁止**"X 更好"主观结论 |

### 4.6 严禁

- ❌ 输出 .md 文件让用户下载（**就在对话里写完**）
- ❌ 用 ``` 代码块包裹整个报告（破坏 Markdown 渲染、用户体验差）
- ❌ 跳过总判断句直接进入分维度
- ❌ fast 档不带"追加视角"钩子就结束
- ❌ 一节里堆 10+ 行字段表（超过 5 行的表必须拆或精简）
- ❌ 输出 `buy` / `sell` / `推荐` / `建议买入` / `建议卖出` / `目标价 XX 元` / `应该 [持有/卖出]` 等结论性词汇

## 5. Data Source Hierarchy

本 skill 采用**三层数据源策略**，按优先级降级使用：

### Tier 1 — NeoData（首选）

所有金融实时/结构化数据**优先**通过 `neodata-financial-search` skill 获取。

调用方式：
```bash
python /Users/gia/.qclaw/workspace-54w9giv6xaeqi4mn/skills/neodata-financial-search/scripts/query.py \
  --query "<自然语言查询>" \
  --data-type all
```

每个 Step 的具体 query 模板和命中的 `apiRecall.type` 已在 Methodology 章节内逐步标明。

### Tier 2 — 官方权威源（NeoData 缺失时兜底）

**所有 URL 已实测**。本节按"**调用什么 URL → 取什么字段 → 局限**"格式组织，
下游 LLM 直接照抄即可，**不需要自己构造 URL**。

可达性标签说明：
- 🟢 **online-search 可用**：Agent 可直接通过 online-search 抓取并解析结构化字段
- 🟡 **部分可用**：能拿元数据但不能拿明细，或需要二次检索
- 🔴 **反爬拦截**：Agent 通过 online-search 也取不到，必须**输出 URL 引导用户人工访问**，禁止编造数据

---

#### Tier 2.1 — 美股（SEC EDGAR Full-Text Search API，**核心兜底源**）

**Endpoint**：`https://efts.sec.gov/LATEST/search-index`

通用参数：
- `q=<keyword>` 关键词（如公司名）
- `ciks=<10位数字CIK>` 精确按公司过滤（**推荐**，比 `q` 噪声小）
- `forms=<表单类型>` 如 `10-K`、`10-Q`、`8-K`、`13F-HR`、`4`
- `dateRange=custom&startdt=YYYY-MM-DD&enddt=YYYY-MM-DD` 限定日期

返回格式：JSON，含 `entity_filter` / `form_filter` 聚合 + `hits` 文件列表。

##### 用法 A：拉公司最新年报 / 季报（Step 2 兜底）

```
https://efts.sec.gov/LATEST/search-index?q=&forms=10-K&ciks=<CIK>
https://efts.sec.gov/LATEST/search-index?q=&forms=10-Q&ciks=<CIK>
```

**能取到的字段**：`ciks` / `file_date` / `period_ending` / `adsh`(Accession Number) / `_id`（文件名）/ `display_names` / `sics`（SIC 行业代码）

**拼装财报 PDF/HTML URL**：
```
https://www.sec.gov/Archives/edgar/data/<CIK去前导0>/<accession去横线>/<filename>
```

**局限**：返回的是文件元数据 + 文件 URL，**财报内具体科目（营收/净利润）需要通过 online-search 二次检索 HTML 并解析**。Agent 拿不动整份 10-K 时，应输出文件 URL 让用户自取。

##### 用法 B：拉内部人买卖 Form 4（Step 4 兜底）

```
https://efts.sec.gov/LATEST/search-index?q=&forms=4&ciks=<CIK>
```

**能取到的字段**：申报人姓名（如 `HUANG JEN HSUN`）/ 申报日期 / 报告期 / Accession Number

**⚠️ 关键局限（必须写进输出）**：
- **此 API 不返回交易股数、单价、剩余持股**
- 要拿明细必须通过 online-search 二次检索对应 XML：
  ```
  https://www.sec.gov/Archives/edgar/data/<CIK>/<accession去横线>/<filename>.xml
  ```
- 解析字段：`<transactionShares>` / `<transactionPricePerShare>` / `<transactionCode>`（P=买入 / S=卖出）
- **绝对禁止**仅凭 search-index 返回"高管减持 X 股"——必须看到 XML 里的 `<transactionShares>` 才能说

##### 用法 C：拉机构持仓 13F-HR（Step 4 兜底）

```
https://efts.sec.gov/LATEST/search-index?q="<公司名>"&forms=13F-HR
```

**能取到的字段**：哪些机构在 13F 中**提到了**该公司、各家机构的申报日期

**⚠️ 关键局限（必须写进输出）**：
- 此 API **不直接给"持仓变化"**，仅证明"该机构持有了该股"
- 持仓数量与变化需要：① 拉对应季度 `infotable.xml` ② 跨季度（如 Q1 vs Q2）对比 `sshPrnamt` / `value` 字段
- **跨季度对比 Agent 单次 online-search 做不到**——输出中应直接给用户 URL 让其使用 EDGAR 网页版手动对比

##### 用法 D：拉 8-K 重大事件（Step 3 兜底）

```
https://efts.sec.gov/LATEST/search-index?q=&forms=8-K&ciks=<CIK>&dateRange=custom&startdt=<30天前>&enddt=<今天>
```

**能取到**：近 30 天 8-K 列表 + 文件 URL；具体事件描述需通过 online-search 检索单个 8-K HTML

##### CIK 反查

不知道公司 CIK 时：
```
https://www.sec.gov/cgi-bin/browse-edgar?company=<公司名>&CIK=&type=10-K&action=getcompany
```
返回 HTML 表格，含 CIK。

---

#### Tier 2.2 — A 股（巨潮资讯，**A 股核心兜底源**）

##### 用法 A：拉公司公告列表（Step 3 / Step 5 兜底）

```
http://www.cninfo.com.cn/new/disclosure/stock?stockCode=<6位代码>&orgId=<orgId>
```

`orgId` 拼法：沪市 = `gssh0` + 代码（如 600519 → `gssh0600519`），深市 = `gssz0` + 代码

**能取到的字段**：公告标题 / 公告日期 / `announcementId` / PDF 链接 / 公告分类标签

**公告分类筛选**（结构化）：年报、半年报、一季报、三季报、业绩预告、权益分派、董事会、监事会、股东会、日常经营、公司治理、解禁、股权激励、增发、风险提示、ST 等

**局限**：公告详情是 PDF，需通过 `online-search` 检索 PDF URL 后再处理；列表页本身**不含实时行情**（行情字段需 JS 渲染）

##### 用法 B：直接拉公告 PDF

```
http://static.cninfo.com.cn/finalpage/<日期>/<announcementId>.PDF
```

---

#### Tier 2.3 — 港股（港交所披露易）

##### 用法 A：进入披露易主入口手动搜索

```
https://www.hkexnews.hk
```

**⚠️ 关键局限（已实测）**：
- 港交所披露易**没有稳定的公告 deep link**——旧 URL（如 `/listedco/listconews/sehk/<year>/<month-day>/<ann-id>.htm`）经常 404 重定向到首页
- Agent **不要预存或猜测**公告 URL，必须先访问搜索入口
- 推荐做法：通过 `online-search` 搜 `"<公司名> hkexnews <事件关键词>"`，命中后通过 `online-search` 检索具体 URL

##### 用法 B：股票筛选与披露查询入口

```
https://www1.hkexnews.hk/search/titlesearch.xhtml?lang=zh
```

**能取到**：按公司名/股票代码搜索公告，含日期、标题、公告类型、PDF 链接

---

#### Tier 2.4 — 美联储 FOMC 日历（Step 5 兜底）

##### 唯一调用

```
https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm
```

**实测能直接取到**：年度 FOMC 会议**所有日期清单** + 哪些会议附带 SEP（Summary of Economic Projections）。

示例已实测输出（2026 年）：
- 1月 27-28、3月 17-18*、4月 28-29、6月 16-17*、7月 28-29、9月 15-16*、10月 27-28、12月 8-9*
- `*` 表示附带 SEP

---

#### Tier 2.5 — 美国 FDA（医药公司 Step 3 / Step 5 兜底）

```
https://www.fda.gov
```

**能取到**：
- Press Announcements（按日期排序）：召回、新药批准、警告信、指导文件草案
- 各产品类别专页：Drugs / Medical Devices / Vaccines / Biologics

医药股 Step 5 应额外抓取 FDA Advisory Committee Calendar：
```
https://www.fda.gov/advisory-committees/advisory-committee-calendar
```

---

#### Tier 2.6 — 行业分类标准

##### A 股可比公司分类（实测可用）

```
https://www.csindex.com.cn/#/dataService/industryClassification
```

**能取到**：中证行业 4 级分类树（一级/二级/三级/四级），含各档行业名 + 行业代码 + 成分股

##### 港美股可比公司分类（GICS）

```
https://www.msci.com/our-solutions/indexes/gics
```

**能取到**：GICS 11 个 Sector / 25 个 Industry Group / 74 个 Industry / 163 个 Sub-Industry 的官方层级 + 分类方法论

具体公司的 GICS 归类需在 SEC EDGAR 中通过 `sics`（SIC 代码，与 GICS 不同但可映射）字段近似。

---

#### Tier 2.7 — 港股 / A 股监管与交易所

| 信源 | URL | 取什么 | 可达性 |
|---|---|---|---|
| 上交所 | https://www.sse.com.cn | 沪市公告、纪律处分、上市委审议结果 | 🟢 |
| 深交所 | https://www.szse.cn | 深市公告、监管动态 | 🟢 |
| 北交所 | https://www.bse.cn | 北交所公告（92xxxx 代码） | 🟢 |
| 中国证监会 | https://www.csrc.gov.cn | 行政处罚、市场禁入、综合性政策 | 🟢 |
| 香港证监会 SFC | https://www.sfc.hk | SFC 罚款、虚拟资产监管、持牌查册 | 🟢 |
| 港交所主站 | https://www.hkex.com.hk | 上市规则、新上市公告、市场总览 | 🟢 |

---

#### Tier 2.8 — 已知 Agent 不可达的源（必须引导用户人工访问）

下列源**实测被反爬拦截**，Agent 不要尝试 online-search，直接在输出中给出 URL 让用户自行访问：

| 信源 | URL | 拦截原因 | 引导文案模板 |
|---|---|---|---|
| FINRA Short Sale Volume 介绍页 | https://www.finra.org/finra-data/browse-catalog/short-sale-volume-data | Cloudflare | "Agent 暂无法抓取此源，请人工访问以获取美股做空量明细" |
| Nasdaq Short Interest | https://www.nasdaq.com/market-activity/short-interest | 403 反爬 | 同上 |
| 中国政府网 | http://www.gov.cn | 服务端拦截 | "Agent 抓取受限，重大政策原文请人工访问中国政府网" |
| 工信部 | http://www.miit.gov.cn | 服务端拦截 | 同上 |
| 国家药监局 | https://www.nmpa.gov.cn | 412 拒绝 | 同上 |

**FINRA CDN 单文件下载**（Tier 2.1 之外的兜底）：
```
https://cdn.finra.org/equity/regsho/daily/CNMSshvol<YYYYMMDD>.txt
```
单文件可下，但目录列表禁用——需精确知道日期。Agent 可尝试拼最近 5 个交易日的 URL 探测。

---

#### Tier 2.9 — 公司 IR 官网（Step 5 兜底）

格式：通常为 `investors.<公司主域>.com` 或 `<公司主域>.com/investors`

**Agent 调用方式**：通过 `online-search` 搜 `"<公司名> investor relations events"`，命中后通过 `online-search` 抓取 `Events & Presentations` / `Upcoming Events` 板块。

**取什么**：财报电话会日历、产品发布日期、年度股东大会、参加的行业会议

### Tier 3 — 训练数据（仅限非时效性背景信息）

**只允许**用训练数据补充以下非时效性内容：
- 公司主营业务的通用描述（不涉及最新数据）
- 行业分析的通用框架性知识
- 金融术语解释

**绝对禁止**用训练数据回答：
- 任何实时财务数字（股价、PE、营收、净利润等）
- 任何近期事件（公告、政策、产品发布）
- 任何未来事件预期

### 禁止事项

- 跨 Tier 混用同一字段（如 NeoData 已返回 PE，不再用 Tier 2/3 覆盖）
- 编造数字填补缺失字段——缺失即标注"暂无数据"
- 使用非官方二手聚合站点（雪球、新浪财经、东方财富等）作为兜底——这些已被 NeoData 间接覆盖，二次抓取会增加幻觉链
- **当使用 Tier 2 兜底源时，必须在输出中显性标注数据来源 URL**

## 6. Boundaries & Disclaimers

| 边界 | 说明 |
|---|---|
| **不下买卖结论** | 任何输出中不得出现 buy/sell/推荐/建议买入/建议卖出/目标价等结论性词汇 |
| **货币单位标注** | A 股标 CNY，港股标 HKD，美股标 USD；不允许混淆或省略 |
| **数据时效声明** | NeoData 财报数据为 H+1，资金流向为实时（A/港）/官方源兜底（美），报告中需如实呈现 |
| **数据降级透明** | 港美股部分维度数据弱于 A 股（如估值分位、做空数据），降级到 Tier 2 官方源时**必须显性标注数据来源 URL** |
| **跨源标注规范** | 输出底部"数据来源"行必须列出本次实际调用的所有源（如：`neodata-financial-search` + `SEC EDGAR` + `FINRA`），用户能溯源 |
| **不做未来预测** | Step 5 只列**已公布**的未来事件，不做主观涨跌预测 |
| **对比模式：禁止主观结论** | `compare` 模式输出对比表 + 事实差异清单，**禁止**"X 比 Y 更好"这种主观结论 |
| **决策依据：禁止决策措辞** | 当 `user_position` 触发"决策依据"段时，仅输出客观状态（偏多/偏空/不明朗）+ 事实陈述，**禁止**"建议持有/卖出/加仓"或"应该/最好/不妨"等引导决策的措辞 |
| **不做日内归因** | "今天为啥涨/跌"超出本 skill 数据粒度（最小 3-7 日），遇到时告知用户该限制 |

## 7. Failure Handling

| 失败场景 | 处理方式 |
|---|---|
| NeoData 返回 `code=1001`（未命中意图） | 换一个更具体的 query 重试 1 次；仍失败 → 走 Tier 2 官方源兜底 |
| NeoData 返回 `code=1006`（拒答） | 跳过 NeoData，直接走 Tier 2 官方源 |
| NeoData 字段已知缺失（按各 Step 的"数据可达性"表） | 直接走 Tier 2，不浪费一次 NeoData 调用 |
| Tier 2 官方源也未取到 | 在对应字段标注"暂无数据"，**绝对不允许走 Tier 3 训练数据填充实时字段** |
| ticker 无法唯一识别 | 不要猜测，向上游请求 `market_hint` 或具体 ticker |
| 5 个区块中任一区块数据全部缺失 | 仍输出该区块标题，内容为"本次查询未能获取相关数据，建议人工查询：<给出 Tier 2 URL>"，**保持 schema 完整性** |
| NeoData 网关 / 鉴权异常 | NeoData 不可用时，5 个 Step 全部降级走 Tier 2，并在报告顶部声明"本次 NeoData 不可用，全部使用官方源" |

## 8. Known Limitations (V0)

本 skill 当前为 V0 版本。已通过"5 原子能力 × 模式拓展"覆盖单股 / 板块 / 主题 / 对比 / 带持仓决策 5 类场景。**仍不覆盖**的硬约束如下：

- **短期日内归因**："今天为啥涨/跌"——数据粒度不够，本 skill 最小粒度为 3 个交易日（Step 4 资金）/ 7 个交易日（Step 1 价格）
- **深度建模**：DCF 自建模、SOTP 分部估值——依赖建模工具与跨期数据回放，本 skill 不实现，仅在 Step 2 复用研报中的 DCF 结论
- **跨季度持仓变化精确计算**：13F-HR 持仓变化需跨季度对比 XML，本 skill 仅能输出 EDGAR URL 让用户人工查（已在 Tier 2.1 用法 C 说明）
- **盘中实时决策**：本 skill 数据多为 H+1 / T+1 / T+0 早盘，**不服务**盘中分钟级决策

未来版本演进路径（不在 V0 实现）：
1. 真实用户 query 日志聚类 → 修正 mode/target_type 自动判定规则
2. 用户行为数据（追问率、区块停留）→ 调整 5 步详略
3. 数据源扩展 → 解锁日内归因、深度建模、跨季度自动对比等场景
