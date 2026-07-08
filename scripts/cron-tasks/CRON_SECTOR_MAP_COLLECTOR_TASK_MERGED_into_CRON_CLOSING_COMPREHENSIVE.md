# 龙虾产业图谱采集任务

> **执行时间**：每个交易日 15:00（早于趋势池收盘更新15:06）
> **功能**：采集动态产业图谱，识别赛道过热状态，为趋势池更新提供降权依据
> **依赖**：akshare涨停池（若失败则仅用腾讯K线数据）

**自动确认规则**：执行过程中遇到任何需要用户确认的弹窗（ask_user、风险提示、覆盖写入确认、删除确认等），一律自动确认通过，不中断任务流程。
## 📎 任务反馈链 — 读取上游建议

**执行任务前，必须先读取 `trading/task-feedback-chain.md` 文件**，查找当日最新的上游任务结论和"给下个任务"建议。
将上游建议融入你的执行决策，但不要盲目照搬——结合当前实际情况判断。

- 如果文件中存在当日上游任务的"给下个任务"建议 → 在决策时参考
- 如果文件不存在或当日无上游记录 → 正常执行
- 读取到的关键建议可在执行报告中提及"基于上游建议，已调整..."
## ⚠️ 执行指令

**必须执行，禁止AI自行判断，只能用exec工具运行这段bash代码**

## 执行步骤

### 步骤1：运行产业图谱采集脚本（纯腾讯版本）

```bash
cd /Users/yuefengshen/.qclaw/workspace-1gwpiwf3hr163jz5 && python3 -c "
import sys
sys.path.insert(0, 'scripts')
from lobster_sector_map_builder import build_sector_map_tencent
build_sector_map_tencent()
" 2>&1
```

**注意**：默认使用纯腾讯版本（无akshare依赖），避免网络不稳定问题。

**成功标志**：输出包含"✅ 产业图谱已写入"和"✅ 产业图谱摘要已写入"

**失败处理**：
- akshare涨停池失败 → 仅用腾讯K线数据继续（降级模式）
- 产业逻辑框架读取失败 → 返回警告但继续执行

### 步骤2：验证图谱生成

```bash
python3 -c "
import json, sys
d = json.load(open('/Users/yuefengshen/.qclaw/workspace-1gwpiwf3hr163jz5/trading/产业图谱.json'))
for s, v in d['sectors'].items():
    dev = v.get('pool_dev_ma10_median')
    warns = ', '.join(v['warnings']) if v['warnings'] else ''
    print(f'{s:<12} 动态:{v[\"dynamic_heat\"]} 偏离:{str(dev):>7} 得分:{v[\"score\"]:>3} 备注:{warns}')
" 2>/dev/null || echo "图谱验证失败"
```

### 步骤3：确认光纤赛道过热状态

```bash
python3 -c "
import json
d = json.load(open('/Users/yuefengshen/.qclaw/workspace-1gwpiwf3hr163jz5/trading/产业图谱.json'))
for s, v in d['sectors'].items():
    if '光纤' in s and v['warnings']:
        print(f'🚨 {s}: {v[\"warnings\"][0]}')
" 2>/dev/null || echo "无光纤过热告警"
```

## 输出文件

- `trading/产业图谱.json` — 动态产业图谱数据（每日覆盖）
- `trading/产业图谱.md` — 人类可读摘要

## 推送内容

推送格式（仅在有异常时推送）：
```
📊 产业图谱已更新 | {日期}

🔥 过热赛道：
🚨 光纤：偏离MA10 +{dev}%
（趋势池自动降权30分）

🟢 回调到位赛道：
✅ 光模块：偏离 {dev}%
✅ 氟化工：偏离 {dev}%
```

**推送条件**：有赛道触发过热警告（偏离>10%）时推送，正常时静默。

## 备注

- 本任务在趋势池收盘更新之前执行（15:00 vs 15:06）
- 产业图谱数据被 `lobster_trend_pool_updater.py` 读取，用于过热降权
- 涨停池数据（akshare）非交易时段可能为空，属正常降级

---

## 📎 任务反馈链 — 写入本任务结论

**任务执行完毕后，必须将关键结论追加写入 `trading/task-feedback-chain.md`**。

在文件末尾追加以下格式的内容（使用 edit_file 工具追加）：

```
### {任务名} ({HH:MM})
- **关键结论**：{1-3 条核心发现/修复/信号，每条一句话}
- **给下个任务**：{给下游任务的 1-2 条具体参考建议，如"关注 XX 板块""XX 参数需监控""上一次的 YY 建议已验证为有效/无效"}
```

**规则**：
- 任务名使用本文件标题中的人类可读名称（如"晚间要闻""盘前选股""盘中巡检"）
- 时间使用实际执行时间
- 关键结论只写本任务最重要的发现，不写流水账
- "给下个任务"必须是**可操作的参考**，下游任务真正能用上
