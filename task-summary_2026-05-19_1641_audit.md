# 龙虾系统全面审计 2026-05-19 16:41

## 已修复问题

### 🔴 Critical: 盘前选股引擎趋势池解析索引错位（已修）
- 根源：趋势容量池 v2.1 新增4列（赛道状态、MA20、总市值、总分），`get_trend_pool()` 列索引未更新
- 影响：3.0趋势低吸候选永远为空（`status`读到了MA5数值、`✅`读到了MA10数值）
- 修复：重映射列索引 + `select_30_trend` 中从 `note` 字段检查 `✅`

### 🔴 Critical: 腾讯K线解析 qfqday 字段缺失（已修）
- 根源：历史K线API返回 `qfqday` 字段，代码只查了 `qfq` → 仅科创板688系能命中
- 影响：42只种子股一度只有2只有效数据，修复后42/42全部命中
- 修复：`get_tencent_kline()` 改按 `qfq+day→qfq→day` 顺序查找

### ⚠️ Medium: 7处 qt.gtimg.cn 调用 text=True 编码问题（已修）
- 3个cron文件的7处 subprocess.run 用 text=True 取腾讯GB2312数据
- 影响：cron任务偶发 UnicodeDecodeError 挂掉
- 修复：统一改为手动多编码回退（GB2312→GBK→UTF-8）

### ✅ 数据逻辑分离（已完成）
- 42只种子股从脚本硬编码迁移到 `lobster-config.json`，周日进化直接改配置

## 现存问题（待修）

### ⚠️ Medium: verify_rules.sh 只检查文件存在，未校验配置一致性
- 仅22行，只检查文件是否存在 + 大小
- 建议：增加配置值一致性校验（如情绪规则值、趋势池阈值）

### 💡 Minor: 三套打分系统未统一
- `scoring_calculator.py`: 50分制加权分
- `trend_pool_updater.py`: 100分制加权分（35分入池）
- `premarket_engine.py`: 简易分（仅前端排序参考）
- 这个设计合理——用途不同不需要统一，但建议在文档标注

### ✅ 确认正常项
- 数据流：盘前→竞价→关注股→复盘，字段名完全对齐
- bid_filter: 逻辑干净，4个维度过滤阈值合理
- scoring_calculator: 模块化设计，参数化输入
- config vs rules: 仓位上限/情绪规则值一致
