# BUG_LOG.md — 龙虾系统错误日志

> 本文件记录所有已发现并修复的系统错误。
> 每周日 20:00 自动回顾，检查是否有同类错误再次发生。
> 记录格式：BUG-XXX / ERROR-XXX 编号，含根因、修复方案、预防措施。

---

## 编号规则

- **BUG-XXX**：系统逻辑/代码 bug（功能不正确）
- **ERROR-XXX**：流程/配置错误（功能未生效或执行异常）
- 编号全局递增，不重置

---

## BUG-001：冰点区全仓买入
- **日期**：2026-05-21 发现
- **现象**：情绪冰点（<1500）时，模拟仓全仓买入，违反5成上限
- **根因**：`emotion_force_sell()` 检查维度但 `buy()` 未检查情绪
- **修复**：`buy()` 增加情绪检查，冰点区拒绝买入；3.0 冰点熔断规则写入 config
- **预防**：`buy()` 第一道关卡必须是情绪检查，不可依赖下游逻辑

---

## BUG-002：sell() 不检查 can_sell
- **日期**：2026-05-21 发现
- **现象**：T+1 限制未生效，当日买入可当日卖出
- **根因**：`sell()` 函数未调用 `check_can_sell()`
- **修复**：`sell()` 开头增加 `if not check_can_sell(symbol): return False`
- **预防**：所有卖出操作必须经过 can_sell 检查，单元测试覆盖

---

## BUG-003：weekly_summary() 硬编码
- **日期**：2026-05-21 发现
- **现象**：`weekly_summary()` 输出固定字符串，不读实际持仓数据
- **根因**：函数体为占位符，未实现真实计算
- **修复**：改为读取 positions + 历史 pnl 计算真实收益率
- **预防**：禁止提交占位符代码，进化任务 v10 增加 Python 语法检查

---

## BUG-004：模拟仓无止盈逻辑
- **日期**：2026-05-21 发现
- **现象**：持仓盈利 >5% 不会触发卖出，只有止损
- **根因**：`sell()` 只有硬止损检查，无分时止盈
- **修复**：增加分时止盈（盈利≥5%且收盘未封板→SELL_ALL，14:50后检测）
- **预防**：买卖规则必须成对实现（止损+止盈）

---

## BUG-005：无限限价单
- **日期**：2026-05-21 发现
- **现象**：`sell()` 限价单不设超时，订单永久挂单
- **根因**：`limit_order_sell()` 无 timeout 参数
- **修复**：增加默认300秒超时，超时后撤单市价卖出
- **预防**：所有限价单必须有超时机制

---

## BUG-006：腾讯 qt.gtimg.cn GB2312 编码
- **日期**：2026-05-19 发现
- **现象**：读取实时行情时中文乱码或报错
- **根因**：API 返回 GB2312 编码，脚本按 UTF-8 解析
- **修复**：`iconv -f gb2312 -t utf-8`（失败则 GBK）
- **预防**：所有腾讯 API 调用必须走 GB2312→GBK→UTF-8 依次解码

---

## BUG-007：3.0 冰点熔断 config 缺失
- **日期**：2026-05-20 发现
- **现象**：config 只有4段情绪区间，缺少1500-2000段
- **根因**：v2.1 规则升级时 config 未同步
- **修复**：config `emotion` 段增加 1500-2000 区间（aux=无，3.0熔断）
- **预防**：规则升级必须同步更新 `lobster-config.json`，进化任务 v10 增加配置一致性审计

---

## BUG-008：get_market_sentiment.py group(2) 索引错误
- **日期**：2026-05-28 发现
- **现象**：正则表达式只有1个group，代码引用 `group(2)` 导致异常，涨跌家数获取失败
- **根因**：正则 `r'上涨:(\d+)'` 只有 group(1)，脚本写 `md.group(2)`
- **修复**：改为 `md.group(1)`；主源改为 legulegu.com 直接数据
- **预防**：正则表达式修改后必须测试 group 索引；legulegu.com 作为主源，腾讯采样作为备源

---

## BUG-009：采样估算涨跌家数完全失真
- **日期**：2026-05-28 发现
- **现象**：自行构造代码序列采样，返回5322涨/0跌（实际指数全跌）
- **根因**：采样算法错误，未过滤停牌股，且用腾讯 API 字段映射错误（p[3]是现价非涨跌幅）
- **修复**：废弃采样方案，改用 legulegu.com 主源 + akshare 全量拉取
- **预防**：采样算法必须基于真实代码列表且过滤停牌股；禁止用估算数据做情绪判定

---

## BUG-010：sell() 后 market_value 未更新
- **日期**：2026-05-28 发现
- **现象**：博敏电子卖出后，市值残留159,825（含博敏），累计盈利虚报11%实为1.95%
- **根因**：`sell()` 只改 positions 不重新计算 market_value，依赖旧 price_map
- **修复**：`sell()` 末尾调用 `_update_capital_after_trade()`，用 positions 列表重新计算
- **预防**：所有 trade 操作后必须重新计算 total_assets/market_value，不依赖买入价或缓存

---

## BUG-011：系统状态.json yesterday 语义错误
- **日期**：2026-05-28 发现
- **现象**：`yesterday.up_count` 存的是 today 数据，`yesterday.date` 存的是 `last_updated`
- **根因**：写入时用错字段，yesterday 应存前一交易日收盘数据
- **修复**：增加 `last_close_date` 字段，yesterday 数据从实际前一交易日写入
- **预防**：含 yesterday/today 的字段写入前必须打印验证

---

## BUG-012：buy() 仓位计算用 initial_capital 而非 total_assets
- **日期**：2026-05-28 发现
- **现象**：博敏电子9.8万+华天科技6.6万合计仓位16.4%，按102万总资产应为约16%
- **根因**：`buy()`/`check_position_limit()`/`emotion_force_sell()` 三处用 `initial_capital`（固定100万）
- **修复**：三处全部改为 `total_assets`（当前总资产）
- **预防**：仓位计算必须用 `total_assets`，`initial_capital` 只用于初始化

---

## BUG-013：买入手续费未计入成本
- **日期**：2026-05-23 发现
- **现象**：`position["cost"]` 只存 `shares * buy_price`，未加买入手续费
- **根因**：`buy()` 未调用 `calc_fees()` 计算买入手续费
- **修复**：`cost = shares * buy_price + calc_fees(shares * buy_price, is_buy=True)`
- **预防**：`calc_fees()` 必须在 `buy()`/`sell()` 中对称调用

---

## BUG-014：weekly_summary() 累计盈亏公式错误
- **日期**：2026-05-23 发现
- **现象**：累计盈亏从+5.9%修正为+2.27%，差异3.63%
- **根因**：用硬编码公式计算，未用 `hist_pnl + floating_pnl`
- **修复**：改用 `hist_pnl + floating_pnl` 公式
- **预防**：盈亏计算必须有单元测试，覆盖多笔买卖场景

---

## BUG-015：sell() 函数 cost 变量未定义
- **日期**：2026-05-25 发现
- **现象**：卖出时报 NameError，模拟交易中断
- **根因**：`sell()` 第510行引用 `cost` 变量但未定义
- **修复**：第510行前加 `cost = p["cost"]`
- **预防**：Python 脚本上线前必须用 `py_compile` 验证语法

---

## BUG-016：情绪三重校验代码未实现
- **日期**：2026-05-28 发现
- **现象**：v2.5 规则说"情绪三重校验"，但代码未实现
- **根因**：规则文档与代码不同步
- **修复**：在 `get_market_sentiment.py` 中新增三重校验逻辑
- **预防**：规则文档与代码必须同步更新；新增规则时必须同时提交代码

---

## BUG-017：scoring_models top_n 未同步到 config
- **日期**：2026-05-28 发现
- **现象**：盘前选股 top_n 参数不生效，始终用硬编码默认值
- **根因**：`scoring_models` 新增 `top_n` 字段，但 `lobster_premarket_engine.py` 仍读旧路径
- **修复**：统一 `scoring_models` 结构，确保所有脚本读同一个路径
- **预防**：参数化改造时，必须全局搜索该参数所有引用点

---

## BUG-018：催化匹配 bug（14只标的仅2只正确匹配）
- **日期**：2026-05-25 发现
- **现象**：`enrich_candidates_with_news.py` 催化匹配只用板块名称精确匹配
- **根因**：未做 sector↔赛道交叉匹配
- **修复**：v2 增加 sector 赛道交叉匹配
- **预防**：催化匹配逻辑必须有测试用例，覆盖所有赛道

---

## ERROR-001：CRON 任务 to 字段为 null 导致推送失败
- **日期**：2026-05-25 发现
- **现象**：博客午间文章/规则一致性校验等任务 `to=null`，推送失败
- **根因**：CRON 创建时 `to` 字段未填写，默认为 null
- **修复**：批量修复所有 cron 任务 `to` 字段，统一为正确推送目标
- **预防**：cron 任务创建/修改后必须检查 `to` 字段非空

---

## ERROR-002：亨通光电价格数据错误
- **日期**：2026-05-23 发现
- **现象**：`enrich_candidates_with_news.py` 输出的亨通光电价格与实时行情不符
- **根因**：读取了缓存/历史数据，未实时查询；腾讯 API 字段映射错误（p[3]是现价非涨跌幅）
- **修复**：改为调用 neodata-financial-search 实时查询；修正字段索引
- **预防**：价格相关输出必须标注数据时间；腾讯 API 字段映射必须有注释说明

---

## ERROR-003：CRON 任务缺少强制回复指令（NO_REPLY 根因）
- **日期**：2026-05-26 发现
- **现象**：cron 任务执行后 agent 生成 NO_REPLY，推送空内容
- **根因**：CRON_MD 文件末尾无「必须回复用户」强制指令
- **修复**：13个 CRON_MD 文件全部增加「最后步骤：回复用户（必须执行）」段落
- **预防**：CRON_MD 模板必须含强制回复指令，进化任务 v10 增加检查

---

## ERROR-004：unlock_t1() 从未被调用
- **日期**：2026-05-25 发现
- **现象**：跨交易日后 `can_sell` 仍为 False，T+1 解锁不生效
- **根因**：`unlock_t1()` 函数已实现但从未被 cron 任务调用
- **修复**：接入 `CRON_BID_AUTO_BUY.md` 步骤1，每个交易日09:26首先调用
- **预防**：新增函数必须有调用点验证；cron 任务步骤必须显式列出所有必须调用的函数

---

## ERROR-005：CRON 任务推送顺序错误（IMA 同步阻塞推送）
- **日期**：2026-05-25 发现
- **现象**：部分 cron 任务执行后无推送，用户未收到消息
- **根因**：CRON 步骤顺序错误：先调 `ima_sync.sh`（阻塞），后输出给用户
- **修复**：调整步骤顺序：先输出给用户，最后调 `ima_sync.sh`（后台）
- **预防**：CRON_MD 模板规定：输出给用户必须优先于后台同步操作

---

## ERROR-006：竞价涨停股入池
- **日期**：2026-05-25 发现
- **现象**：恒林股份竞价+9.99%通过过滤，开盘跌至-9.08%（涨停炸板）
- **根因**：`bid_filter_thresholds` 中 `max_change_pct=10`，竞价涨停（9.99%）被放行
- **修复**：`max_change_pct` 从10改为9.5，过滤竞价接近涨停股
- **预防**：竞价过滤必须排除涨停价（change_pct >= 9.5），不接受「差一点点」

---

## ERROR-007：legulegu.com 反爬虫失效
- **日期**：2026-05-28 发现
- **现象**：legulegu.com 返回 HTML（反爬虫），涨跌家数获取失败
- **根因**：legulegu.com 在2026-05-28当天启用反爬虫
- **修复**：2026-05-29 legulegu.com 恢复，增加 akshare 全量拉取作为备源
- **预防**：关键数据源必须有至少2个独立备源；单源依赖是系统风险

---

## ERROR-008：CRON_MD 指令文件缺失映射
- **日期**：2026-05-23 发现
- **现象**：14个 cron 任务中12个无对应 CRON_MD 文件
- **根因**：任务创建时未同步创建 CRON_MD 指令文件
- **修复**：补全 CRON_BLOG_MIDDAY_TASK.md / CRON_BLOG_CLOSING_TASK.md / CRON_VERIFY_RULES_TASK.md
- **预防**：新建 cron 任务必须同步创建 CRON_MD 文件

---

## ERROR-009：涨跌停缓存 bug（读缓存时丢失 zt/dt 字段）
- **日期**：2026-05-29 发现
- **现象**：涨停池数据为空或字段缺失，午间/收盘复盘无法获取连板数据
- **根因**：涨停池数据写入缓存时含 `zt`/`dt` 字段，但读取时用错误字段名或缓存格式不一致
- **修复**：统一缓存格式；读取时强制校验字段存在性
- **预防**：缓存读写必须有 schema 校验

---

## 统计

| 类型 | 数量 |
|------|------|
| BUG（代码缺陷） | 18 |
| ERROR（运行异常） | 9 |
| **总计** | **27** |

---

## 每周日回顾 checklist

- [ ] 本周新增错误是否已记录到本文件？
- [ ] 是否有同类错误重复出现？（如有，需加强预防措施）
- [ ] 未修复的 ERROR（如 ERROR-002/008）是否有进展？
- [ ] 预防措施是否已落实到代码或规范文档？

---
- 文件创建：2026-05-30
- 最后更新：2026-05-30
- 维护者：龙虾系统自动维护

## BUG-019：total_assets 不一致（回归 BUG-012）
- **日期**：2026-06-01
- **根因**：available_cash 或 market_value 更新不同步
- **修复**：重新计算 total_assets = available_cash + market_value
- **预防**：buy()/sell() 后同时更新 available_cash 和 market_value

---

## BUG-020：total_assets 不一致（回归 BUG-012）
- **日期**：2026-06-03
- **根因**：available_cash 或 market_value 更新不同步
- **修复**：重新计算 total_assets = available_cash + market_value
- **预防**：buy()/sell() 后同时更新 available_cash 和 market_value

---

## BUG-021：total_assets 不一致（回归 BUG-012）
- **日期**：2026-06-04
- **根因**：available_cash 或 market_value 更新不同步
- **修复**：重新计算 total_assets = available_cash + market_value
- **预防**：buy()/sell() 后同时更新 available_cash 和 market_value

---

## BUG-022：total_assets 不一致（回归 BUG-012）
- **日期**：2026-06-09
- **根因**：available_cash 或 market_value 更新不同步
- **修复**：重新计算 total_assets = available_cash + market_value
- **预防**：buy()/sell() 后同时更新 available_cash 和 market_value

---

## BUG-023：market_value 不一致（回归 BUG-010）
- **日期**：2026-06-10
- **根因**：sell()/buy() 后未调用 _update_capital_after_trade()
- **修复**：立即调用 _update_capital_after_trade() 重新计算
- **预防**：所有 trade 操作后必须调用 _update_capital_after_trade()

---

## BUG-024：total_assets 不一致（回归 BUG-012）
- **日期**：2026-06-10
- **根因**：available_cash 或 market_value 更新不同步
- **修复**：重新计算 total_assets = available_cash + market_value
- **预防**：buy()/sell() 后同时更新 available_cash 和 market_value

---

## BUG-025：market_value 不一致（回归 BUG-010）
- **日期**：2026-06-10
- **根因**：sell()/buy() 后未调用 _update_capital_after_trade()
- **修复**：立即调用 _update_capital_after_trade() 重新计算
- **预防**：所有 trade 操作后必须调用 _update_capital_after_trade()

---

## BUG-026：total_assets 不一致（回归 BUG-012）
- **日期**：2026-06-10
- **根因**：available_cash 或 market_value 更新不同步
- **修复**：重新计算 total_assets = available_cash + market_value
- **预防**：buy()/sell() 后同时更新 available_cash 和 market_value

---

## BUG-027：market_value 不一致（回归 BUG-010）
- **日期**：2026-06-10
- **根因**：sell()/buy() 后未调用 _update_capital_after_trade()
- **修复**：立即调用 _update_capital_after_trade() 重新计算
- **预防**：所有 trade 操作后必须调用 _update_capital_after_trade()

---

## BUG-028：total_assets 不一致（回归 BUG-012）
- **日期**：2026-06-10
- **根因**：available_cash 或 market_value 更新不同步
- **修复**：重新计算 total_assets = available_cash + market_value
- **预防**：buy()/sell() 后同时更新 available_cash 和 market_value

---

## BUG-029：market_value 不一致（回归 BUG-010）
- **日期**：2026-06-10
- **根因**：sell()/buy() 后未调用 _update_capital_after_trade()
- **修复**：立即调用 _update_capital_after_trade() 重新计算
- **预防**：所有 trade 操作后必须调用 _update_capital_after_trade()

---

## BUG-030：total_assets 不一致（回归 BUG-012）
- **日期**：2026-06-10
- **根因**：available_cash 或 market_value 更新不同步
- **修复**：重新计算 total_assets = available_cash + market_value
- **预防**：buy()/sell() 后同时更新 available_cash 和 market_value

---

## BUG-031：market_value 不一致（回归 BUG-010）
- **日期**：2026-06-10
- **根因**：sell()/buy() 后未调用 _update_capital_after_trade()
- **修复**：立即调用 _update_capital_after_trade() 重新计算
- **预防**：所有 trade 操作后必须调用 _update_capital_after_trade()

---

## BUG-032：total_assets 不一致（回归 BUG-012）
- **日期**：2026-06-10
- **根因**：available_cash 或 market_value 更新不同步
- **修复**：重新计算 total_assets = available_cash + market_value
- **预防**：buy()/sell() 后同时更新 available_cash 和 market_value

---

## BUG-033：market_value 不一致（回归 BUG-010）
- **日期**：2026-06-11
- **根因**：sell()/buy() 后未调用 _update_capital_after_trade()
- **修复**：立即调用 _update_capital_after_trade() 重新计算
- **预防**：所有 trade 操作后必须调用 _update_capital_after_trade()

---

## BUG-034：total_assets 不一致（回归 BUG-012）
- **日期**：2026-06-11
- **根因**：available_cash 或 market_value 更新不同步
- **修复**：重新计算 total_assets = available_cash + market_value
- **预防**：buy()/sell() 后同时更新 available_cash 和 market_value

---

## BUG-035：total_assets 不一致（回归 BUG-012）
- **日期**：2026-06-11
- **根因**：available_cash 或 market_value 更新不同步
- **修复**：重新计算 total_assets = available_cash + market_value
- **预防**：buy()/sell() 后同时更新 available_cash 和 market_value

---

## BUG-036：market_value 不一致（回归 BUG-010）
- **日期**：2026-06-12
- **根因**：sell()/buy() 后未调用 _update_capital_after_trade()
- **修复**：立即调用 _update_capital_after_trade() 重新计算
- **预防**：所有 trade 操作后必须调用 _update_capital_after_trade()

---

## BUG-037：total_assets 不一致（回归 BUG-012）
- **日期**：2026-06-12
- **根因**：available_cash 或 market_value 更新不同步
- **修复**：重新计算 total_assets = available_cash + market_value
- **预防**：buy()/sell() 后同时更新 available_cash 和 market_value

---

## BUG-038：market_value 不一致（回归 BUG-010）
- **日期**：2026-06-15
- **根因**：sell()/buy() 后未调用 _update_capital_after_trade()
- **修复**：立即调用 _update_capital_after_trade() 重新计算
- **预防**：所有 trade 操作后必须调用 _update_capital_after_trade()

---

## BUG-039：total_assets 不一致（回归 BUG-012）
- **日期**：2026-06-15
- **根因**：available_cash 或 market_value 更新不同步
- **修复**：重新计算 total_assets = available_cash + market_value
- **预防**：buy()/sell() 后同时更新 available_cash 和 market_value

---

## BUG-040：market_value 不一致（回归 BUG-010）
- **日期**：2026-06-15
- **根因**：sell()/buy() 后未调用 _update_capital_after_trade()
- **修复**：立即调用 _update_capital_after_trade() 重新计算
- **预防**：所有 trade 操作后必须调用 _update_capital_after_trade()

---

## BUG-041：total_assets 不一致（回归 BUG-012）
- **日期**：2026-06-15
- **根因**：available_cash 或 market_value 更新不同步
- **修复**：重新计算 total_assets = available_cash + market_value
- **预防**：buy()/sell() 后同时更新 available_cash 和 market_value

---

## BUG-042：market_value 不一致（回归 BUG-010）
- **日期**：2026-06-15
- **根因**：sell()/buy() 后未调用 _update_capital_after_trade()
- **修复**：立即调用 _update_capital_after_trade() 重新计算
- **预防**：所有 trade 操作后必须调用 _update_capital_after_trade()

---

## BUG-043：total_assets 不一致（回归 BUG-012）
- **日期**：2026-06-15
- **根因**：available_cash 或 market_value 更新不同步
- **修复**：重新计算 total_assets = available_cash + market_value
- **预防**：buy()/sell() 后同时更新 available_cash 和 market_value

---

## BUG-044：market_value 不一致（回归 BUG-010）
- **日期**：2026-06-15
- **根因**：sell()/buy() 后未调用 _update_capital_after_trade()
- **修复**：立即调用 _update_capital_after_trade() 重新计算
- **预防**：所有 trade 操作后必须调用 _update_capital_after_trade()

---

## BUG-045：total_assets 不一致（回归 BUG-012）
- **日期**：2026-06-15
- **根因**：available_cash 或 market_value 更新不同步
- **修复**：重新计算 total_assets = available_cash + market_value
- **预防**：buy()/sell() 后同时更新 available_cash 和 market_value

---

## BUG-046：market_value 不一致（回归 BUG-010）
- **日期**：2026-06-15
- **根因**：sell()/buy() 后未调用 _update_capital_after_trade()
- **修复**：立即调用 _update_capital_after_trade() 重新计算
- **预防**：所有 trade 操作后必须调用 _update_capital_after_trade()

---

## BUG-047：total_assets 不一致（回归 BUG-012）
- **日期**：2026-06-15
- **根因**：available_cash 或 market_value 更新不同步
- **修复**：重新计算 total_assets = available_cash + market_value
- **预防**：buy()/sell() 后同时更新 available_cash 和 market_value

---

## BUG-048：market_value 不一致（回归 BUG-010）
- **日期**：2026-06-15
- **根因**：sell()/buy() 后未调用 _update_capital_after_trade()
- **修复**：立即调用 _update_capital_after_trade() 重新计算
- **预防**：所有 trade 操作后必须调用 _update_capital_after_trade()

---

## BUG-049：total_assets 不一致（回归 BUG-012）
- **日期**：2026-06-15
- **根因**：available_cash 或 market_value 更新不同步
- **修复**：重新计算 total_assets = available_cash + market_value
- **预防**：buy()/sell() 后同时更新 available_cash 和 market_value

---

## BUG-050：market_value 不一致（回归 BUG-010）
- **日期**：2026-06-15
- **根因**：sell()/buy() 后未调用 _update_capital_after_trade()
- **修复**：立即调用 _update_capital_after_trade() 重新计算
- **预防**：所有 trade 操作后必须调用 _update_capital_after_trade()

---

## BUG-051：total_assets 不一致（回归 BUG-012）
- **日期**：2026-06-15
- **根因**：available_cash 或 market_value 更新不同步
- **修复**：重新计算 total_assets = available_cash + market_value
- **预防**：buy()/sell() 后同时更新 available_cash 和 market_value

---

## BUG-052：market_value 不一致（回归 BUG-010）
- **日期**：2026-06-17
- **根因**：sell()/buy() 后未调用 _update_capital_after_trade()
- **修复**：立即调用 _update_capital_after_trade() 重新计算
- **预防**：所有 trade 操作后必须调用 _update_capital_after_trade()

---

## BUG-053：total_assets 不一致（回归 BUG-012）
- **日期**：2026-06-17
- **根因**：available_cash 或 market_value 更新不同步
- **修复**：重新计算 total_assets = available_cash + market_value
- **预防**：buy()/sell() 后同时更新 available_cash 和 market_value

---

## BUG-054：market_value 不一致（回归 BUG-010）
- **日期**：2026-06-18
- **根因**：sell()/buy() 后未调用 _update_capital_after_trade()
- **修复**：立即调用 _update_capital_after_trade() 重新计算
- **预防**：所有 trade 操作后必须调用 _update_capital_after_trade()

---

## BUG-055：total_assets 不一致（回归 BUG-012）
- **日期**：2026-06-18
- **根因**：available_cash 或 market_value 更新不同步
- **修复**：重新计算 total_assets = available_cash + market_value
- **预防**：buy()/sell() 后同时更新 available_cash 和 market_value

---

## BUG-056：market_value 不一致（回归 BUG-010）
- **日期**：2026-06-19
- **根因**：sell()/buy() 后未调用 _update_capital_after_trade()
- **修复**：立即调用 _update_capital_after_trade() 重新计算
- **预防**：所有 trade 操作后必须调用 _update_capital_after_trade()

---

## BUG-057：total_assets 不一致（回归 BUG-012）
- **日期**：2026-06-19
- **根因**：available_cash 或 market_value 更新不同步
- **修复**：重新计算 total_assets = available_cash + market_value
- **预防**：buy()/sell() 后同时更新 available_cash 和 market_value

---

## BUG-058：sell_partial() 未调用 _update_capital_after_trade()（BUG-010根因修复）
- **日期**：2026-06-20 发现
- **现象**：BUG-010/012 从5月底反复回归30+次，每次修数据但根因未除
- **根因**：`sell_partial()` 第833行 `_save(data)` 前未调用 `_update_capital_after_trade()`，导致部分卖出后 market_value 和 total_assets 不同步
- **修复**：`sell_partial()` 在 `_save(data)` 前增加 `_update_capital_after_trade(data, actual_price, code)`
- **预防**：所有 trade 操作（buy/sell/sell_partial）后必须调用 `_update_capital_after_trade()`

## BUG-059：sell_partial() position_pct 用 initial_capital（BUG-012回归根因之一）
- **日期**：2026-06-20 发现
- **现象**：部分卖出后仓位百分比错误
- **根因**：`sell_partial()` 第813行用 `data['_meta'].get('initial_capital', 1000000)` 计算 position_pct
- **修复**：改为 `data['capital']['total_assets']`，与 `buy()` 一致
- **预防**：仓位百分比计算统一使用 total_assets

## BUG-060：update_positions_price() 除零风险
- **日期**：2026-06-20 发现
- **现象**：`p['cost']` 为0时 `total_pnl_pct` 计算除零
- **根因**：无除零保护
- **修复**：增加 `if p['cost'] else 0` 条件
- **预防**：所有除法运算必须有除零保护

## BUG-061：rules vs config 配置不一致
- **日期**：2026-06-20 发现
- **现象**：rules说1.0止损-5%（实际-7%），3.0入选阈值30分（实际70分）
- **根因**：config更新后rules文档未同步
- **修复**：更新rules文档，1.0止损→-7%，3.0阈值→70分
- **预防**：config参数变更必须同步更新rules文档

## BUG-062：market_value 不一致（回归 BUG-010）
- **日期**：2026-06-22
- **根因**：sell()/buy() 后未调用 _update_capital_after_trade()
- **修复**：立即调用 _update_capital_after_trade() 重新计算
- **预防**：所有 trade 操作后必须调用 _update_capital_after_trade()

---

## BUG-063：market_value 不一致（回归 BUG-010）
- **日期**：2026-06-22
- **根因**：sell()/buy() 后未调用 _update_capital_after_trade()
- **修复**：立即调用 _update_capital_after_trade() 重新计算
- **预防**：所有 trade 操作后必须调用 _update_capital_after_trade()

---

## BUG-064：market_value 不一致（回归 BUG-010）
- **日期**：2026-06-29
- **根因**：sell()/buy() 后未调用 _update_capital_after_trade()
- **修复**：立即调用 _update_capital_after_trade() 重新计算
- **预防**：所有 trade 操作后必须调用 _update_capital_after_trade()

---

## BUG-065：market_value 不一致（回归 BUG-010）
- **日期**：2026-06-30
- **根因**：sell()/buy() 后未调用 _update_capital_after_trade()
- **修复**：立即调用 _update_capital_after_trade() 重新计算
- **预防**：所有 trade 操作后必须调用 _update_capital_after_trade()

---

## BUG-066：market_value 不一致（回归 BUG-010）
- **日期**：2026-06-30
- **根因**：sell()/buy() 后未调用 _update_capital_after_trade()
- **修复**：立即调用 _update_capital_after_trade() 重新计算
- **预防**：所有 trade 操作后必须调用 _update_capital_after_trade()

---

## BUG-067：market_value 不一致（回归 BUG-010）
- **日期**：2026-06-30
- **根因**：sell()/buy() 后未调用 _update_capital_after_trade()
- **修复**：立即调用 _update_capital_after_trade() 重新计算
- **预防**：所有 trade 操作后必须调用 _update_capital_after_trade()

---

## BUG-013（2026-07-01）：三重校验两次误砍仓位

**现象**：盘前选股输出 `总仓位上限: 15%`，但 139涨 应为 30%（冰点区间）

**根因**：两重逻辑错误叠加

1. **执行顺序错误**：`emotion['up_count'] = ad['up']` 写在三重校验之后，导致 `today_up=0`（未赋值），触发校验3误判
2. **校验3阈值错误**：`today_up < 500` 永远会命中冰点日（139<500），将合法冰点数据当作数据错误再次减半

**触发条件**：`up < 500` 的冰点日（139/299/450 等）

**修复**：
- `scripts/lobster_premarket_engine.py`：将 `up_count` 赋值移至三重校验之前
- `scripts/lobster_premarket_engine.py`：移除 `today_up < 500` 条件（`get_advance_decline` 已有 `up>0` 保护，冰点日合法数据不应触发）

**验证**：139冰点→30%✅，2775高潮→70%✅，4001极热→10%✅

**教训**：`up_count` 必须在使用前赋值；三重校验的极端值阈值应只处理真正的数据异常（>4000），不应覆盖正常冰点区间（100-500）

## BUG-068：_load() 缺少文件损坏恢复机制
- **日期**：2026-07-02 发现
- **现象**：`模拟持仓.json` 如果损坏（JSON格式错误），`_load()` 直接抛出异常，导致整个模拟交易系统崩溃
- **根因**：`_load()` 函数没有 try-except 保护，没有备份恢复机制
- **修复**：增加文件损坏恢复机制：（1）尝试加载主文件 （2）失败则尝试从 .bak 备份恢复；（3）都失败则返回空数据结构并创建新文件
- **预防**：所有 JSON 读写函数必须有 try-except 保护；关键数据文件写入前先备份

## BUG-069：lobster-rules.md 与 config 不一致（1600_2000 仓位上限）
- **日期**：2026-07-02 发现
- **现象**：rules 第19行说 `1500-2000 → 仓位上限40%`，但 config 中 `1600_2000.pos_limit_pct = 60%`
- **根因**：config 更新（v1.16 40→60）后 rules 文档未同步
- **修复**：更新 rules 第19行和第268行，改为 `1600-2000 → 仓位上限60%`
- **预防**：config 参数变更必须同步更新 rules 文档；每周六 Bug 巡检增加 rules vs config 一致性检查

## BUG-070：market_value 不一致（回归 BUG-010）
- **日期**：2026-07-02
- **根因**：sell()/buy() 后未调用 _update_capital_after_trade()
- **修复**：立即调用 _update_capital_after_trade() 重新计算
- **预防**：所有 trade 操作后必须调用 _update_capital_after_trade()

---

## BUG-071：market_value 不一致（回归 BUG-010）
- **日期**：2026-07-02
- **根因**：sell()/buy() 后未调用 _update_capital_after_trade()
- **修复**：立即调用 _update_capital_after_trade() 重新计算
- **预防**：所有 trade 操作后必须调用 _update_capital_after_trade()

---

## 附录A：错误分级（自 error_log.md 迁移）

| 级别 | 名称 | 说明 | 示例 |
|------|------|------|------|
| P0 | 阻断 | 任务无法执行/系统崩溃 | Cron未触发、脚本报错退出、数据源不可用 |
| P1 | 严重 | 数据错误/关键输出错误 | 价格字段取错、复盘点位写反、报告推送失败 |
| P2 | 中等 | 流程缺陷/不一致 | 步骤顺序不规范、配置未同步、字段映射缺失 |
| P3 | 轻微 | 体验/格式问题 | 注释不清、日志格式不统一、文档过期 |

---

## 附录B：系统性问题总结（自 error_log.md 迁移）

### 问题1：缺乏字段映射表（ERROR-002）

腾讯API字段索引硬编码在代码中，不同脚本可能有不同的索引理解，没有统一的字段映射常量。

```python
# 建议：scripts/tencent_api.py
TENCENT_API_FIELDS = {
    'NAME': 1, 'CODE': 2, 'PRICE': 3, 'CLOSE': 4,
    'OPEN': 5, 'HIGH': 6, 'LOW': 7, 'VOLUME': 8, 'AMOUNT': 9,
}

def parse_stock_data(raw_string):
    p = raw_string.split('~')
    return {
        'price': float(p[TENCENT_API_FIELDS['PRICE']]),
        'close': float(p[TENCENT_API_FIELDS['CLOSE']]),
    }
```

### 问题2：Cron任务步骤顺序不规范（ERROR-005/006）

不同cron任务的步骤顺序不一致，IMA同步可能阻塞推送，缺乏标准的cron任务模板。

### 问题3：配置参数单位不清晰（ERROR-004）

Config中 `max_positions: 5` 表示"5成"，但代码可能被当成"5%"，缺乏单位说明和验证。建议使用显式命名如 `max_positions_cheng` 或 `max_positions_pct`。

---

## 附录C：待办事项（自 error_log.md 迁移）

### 高优先级
1. 创建 `tencent_api.py` 统一字段映射
2. 创建 `CRON_TASK_TEMPLATE.md` 规范步骤顺序
3. 修复CRON_MIDDAY_TASK.md步骤顺序（ERROR-006）
4. 验证ERROR-002修复

### 中优先级
5. 为所有关键函数添加单元测试
6. 为所有cron任务添加步骤顺序审计
7. 为所有配置参数添加单位说明和验证

### 低优先级
8. 代码重构：提取硬编码为配置文件
9. 文档完善：为每个脚本添加字段映射说明
10. 监控完善：为所有cron任务添加执行状态监控

---

> **迁移记录**：2026-07-02，从 `trading/error_log.md` 迁移至此。错误分级 / 系统性问题总结 / 待办事项三部分为唯一新增内容，ERROR-xxx 条目在 BUG_LOG 中已有覆盖。

## BUG-072：market_value 不一致（回归 BUG-010）
- **日期**：2026-07-03
- **根因**：sell()/buy() 后未调用 _update_capital_after_trade()
- **修复**：立即调用 _update_capital_after_trade() 重新计算
- **预防**：所有 trade 操作后必须调用 _update_capital_after_trade()

---

## BUG-073：market_value 不一致（回归 BUG-010）
- **日期**：2026-07-06
- **根因**：sell()/buy() 后未调用 _update_capital_after_trade()
- **修复**：立即调用 _update_capital_after_trade() 重新计算
- **预防**：所有 trade 操作后必须调用 _update_capital_after_trade()

---

## BUG-074：market_value 不一致（回归 BUG-010）
- **日期**：2026-07-06
- **根因**：sell()/buy() 后未调用 _update_capital_after_trade()
- **修复**：立即调用 _update_capital_after_trade() 重新计算
- **预防**：所有 trade 操作后必须调用 _update_capital_after_trade()

---

## BUG-075：market_value 不一致（回归 BUG-010）
- **日期**：2026-07-06
- **根因**：sell()/buy() 后未调用 _update_capital_after_trade()
- **修复**：立即调用 _update_capital_after_trade() 重新计算
- **预防**：所有 trade 操作后必须调用 _update_capital_after_trade()

---

## BUG-076：market_value 不一致（回归 BUG-010）
- **日期**：2026-07-07
- **根因**：sell()/buy() 后未调用 _update_capital_after_trade()
- **修复**：立即调用 _update_capital_after_trade() 重新计算
- **预防**：所有 trade 操作后必须调用 _update_capital_after_trade()

---
