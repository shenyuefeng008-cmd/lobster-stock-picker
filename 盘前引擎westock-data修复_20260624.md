# 盘前引擎westock-data数据源修复 — 2026-06-24

## 问题
akshare涨停池接口失效（东财API Python requests层被TLS fingerprint/代理阻断），导致盘前引擎1.0/2.0候选全部为空。

## 根因
- akshare依赖东财push2.eastmoney.com，Python requests在此机器被断开
- pandas模块丢失（已修复pip安装），但即使修复后akshare仍返回0条
- 东财datacenter-web返回"报表配置不存在"

## 解决方案
新增westock-data作为主数据源，akshare降为备用：

### 1. 涨停池（get_yesterday_zt）
- **主源**：westock-data `sector pt02031283`（"昨日涨停"聚源板块），返回完整代码+名称
- **备源**：akshare `stock_zt_pool_previous_em`

### 2. 连板池（get_zt_sub）
- **主源**：westock-data `sector pt02031398`（"昨日连板"聚源板块）
- **备源**：akshare `stock_zt_pool_sub_new_em`

### 3. 连板数交叉推断
涨停池默认1板，通过连板池（2板以上）交叉更新涨停池中的连板数

### 4. 所属行业补充（_enrich_zt_sector）
用westock-data申万二级行业成分股反向匹配：
- 搜索15个核心赛道（半导体/元件/电力/化学制品等）
- 获取各板块成分股代码列表
- 与涨停池代码集合交叉匹配

### 5. ST股过滤
涨停池和连板池均过滤名称含"ST"的股票

## 修改文件
- `scripts/lobster_premarket_engine.py`（5处修改）
  - get_yesterday_zt(): 新增westock-data主源 + akshare备源
  - get_zt_sub(): 新增westock-data主源 + akshare备源
  - _enrich_zt_with_quote(): 改用K线补充成交额（仅连板股）
  - _enrich_zt_sector(): 新增，申万行业反向匹配
  - select_20_sector(): 排除"其他"行业
  - select_10_first_to_second(): 成交额为0时跳过过滤
  - ST股过滤

## 验证结果
- 涨停池：0只 → 96只（过滤ST后）
- 连板池：0只 → 22只（过滤ST后）
- 1.0一进二：0只 → 5只（上海贝岭/华微电子/大连热电等）
- 1.0分歧低吸：0只 → 4只（冰点区暂停，非冰点区正常输出）
- 2.0板块卡位：0只 → 4只（化学制品5家/汽车零部件4家）
- 3.0趋势低吸：3只（不受影响）

## 待优化
1. 首板股成交额为0——需要盘中实时补充或改用K线批量获取
2. 行业匹配仅覆盖15个核心赛道，98只归入"其他"——需扩展赛道列表
3. 行业匹配搜索+成分股拉取耗时约1分钟——可缓存板块成分股数据
