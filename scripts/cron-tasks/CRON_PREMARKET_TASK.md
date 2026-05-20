# 龙虾盘前选股 — cron 任务指令（v4 硬脚本版）

> **v4重大变更**：选股逻辑从AI自由裁量改为确定性Python脚本，保证同一数据同一结果
> **执行时间**：交易日 07:00
> **核心任务**：运行选股引擎 → 发送结果 → IMA同步 → 更新关注股

## ⚠️ 错误处理规则（必须严格遵守）

1. 每执行完一个步骤，立即检查是否成功
2. 如果失败，**立即停止**，调用 `message` 工具发送告警
3. 告警格式：
   【CRON_PREMARKET_TASK 告警 YYYY-MM-DD HH:MM】
   ⚠️ 错误：XXX
   详情：XXX
4. **不等待**晚间修复（01:00），立即通知

---

## 步骤0.5：读取近期催化日历（必做）

> 选股前先扫描 `trading/催化日历.md`，将7日内有催化的赛道标注为**优先级提升**，在候选池输出时附加催化逻辑说明。

```bash
# 读取近期催化
python3 << 'PYEOF'
from datetime import datetime, timedelta
import re

today = datetime.now()
deadline = (today + timedelta(days=7)).strftime('%Y-%m-%d')

with open('/Users/yuefengshen/.qclaw/workspace-1gwpiwf3hr163jz5/trading/催化日历.md') as f:
    content = f.read()

# 提取近期催化区（仅未决事件）
section = re.search(r'## 📌 近期催化事件\(未决\)(.+?)(?:## |---)', content, re.DOTALL)
if section:
    rows = re.findall(r'\| (.+?) \| (.+?) \| (.+?) \| (.+?) \| (.+?) \|', section.group(1))
    near_term = []
    for row in rows:
        date_str = row[0].strip()
        if date_str and date_str not in ['时间', '—']:
            try:
                event_date = datetime.strptime(date_str, '%m月%d日') if '月' in date_str else datetime.strptime(date_str, '%Y-%m-%d')
                if event_date.strftime('%Y-%m-%d') <= deadline:
                    near_term.append((date_str, row[1].strip(), row[2].strip()))
            except:
                pass
    if near_term:
        print(f"📌 未来7日催化事件（{len(near_term)}个）：")
        for d, event, track in near_term:
            print(f"  [{d}] {event} → {track}")
    else:
        print("✅ 未来7日内无已登记催化事件")
else:
    print("⚠️ 未找到近期催化区")
PYEOF
```

**输出说明**：将7日内催化事件作为选股方向的辅助参考——
- 有近期催化的赛道，板块卡位维度（2.0）优先级提升
- 有近期催化的个股，打分结果中附加「🔴有催化」标注
- 若催化已落空，相关赛道降低权重

---

## 步骤0.8：盘前舆情速报

在运行选股引擎前，先获取今日重要新闻/政策，判断是否有影响情绪判定的事件。

**操作**：使用 `tencent-news` 技能搜索今日A股热点新闻。
具体步骤：
1. 读取 tencent-news 技能（路径：`~/Library/Application Support/QClaw/openclaw/config/skills/tencent-news/SKILL.md`）
2. 按技能说明初始化 API Key
3. 搜索关键词：`A股 板块 政策 热点`
4. 从结果中提取**可能影响当日情绪的重大事件**（如降准降息、行业新政、黑天鹅等）
5. **如果有重大事件**：写入 `memory/YYYY-MM-DD.md` 的【舆情速报】章节，并在情绪面板中标注调整因子
6. **如果无重大事件**：记录"今日无重大舆情"，继续执行

> ⚡ 此步骤失败不应阻塞后续流程（舆情为辅助维度），记录错误后继续。

---

## 步骤1：运行确定性选股引擎

```bash
python3 /Users/yuefengshen/.qclaw/workspace-1gwpiwf3hr163jz5/scripts/lobster_premarket_engine.py
```

**成功标志**：输出包含 `✅ 已写入 /tmp/lobster_premarket_candidates.json`

**如果失败**：
- 检查脚本是否存在：`ls -la scripts/lobster_premarket_engine.py`
- 检查数据源连通性：单独运行 `curl -s 'https://qt.gtimg.cn/q=sh000001'` 和 legulegu.com
- 发送告警后退出

## 步骤2：读取JSON结果并格式化发送

```bash
cat /tmp/lobster_premarket_candidates.json
```

读取JSON后，按以下格式发送消息给用户：

```
✅ 龙虾盘前选股 YYYY-MM-DD
- 情绪：XXX涨/XXX跌，XXX涨停/XXX跌停
- 主导维度：X，辅助维度：Y
- 总仓位上限：X成

【1.0一进二候选池】（X只）
1. 股票(代码) — 备注
2. 股票(代码) — 备注
...

【1.0分歧低吸候选池】（X只）
1. 股票(代码) — 备注
...

【2.0板块卡位候选池】（X只）
1. 股票(代码) — 备注
...

【3.0趋势低吸候选池】（X只）
1. 股票(代码) — 备注
...

---
📌 以上为候选池，09:25竞价阶段将从中筛选最优1只/档位
```

## 步骤3：IMA同步

```bash
bash /Users/yuefengshen/.qclaw/workspace-1gwpiwf3hr163jz5/scripts/ima_sync.sh /tmp/lobster_premarket_$(date +%Y-%m-%d).md "龙虾盘前选股 $(date +%Y-%m-%d)"
```

**如果ima_sync.sh不存在或失败**：记录到memory/YYYY-MM-DD.md，晚间修复处理。

## 步骤4：更新关注股.md（覆盖写入）

将JSON中的候选池信息写入 `trading/关注股.md`（盘前版本，09:25会再次覆盖更新）。

## 步骤5：写入每日日志

将选股结果追加到 `memory/YYYY-MM-DD.md` 的【盘前预测】章节。

---

## ❌ 禁止事项

1. **禁止**用AI自由裁量选股，必须使用脚本输出
2. **禁止**修改候选池内容（添加/删除/替换股票）
3. **禁止**预测性表述（"大概率/必然/应该会"），必须用"如果X则Y"
4. **禁止**复读关注股

## ✅ 完成标志

- [ ] 脚本执行成功，JSON已生成
- [ ] 结果已发送给用户
- [ ] IMA已同步（或失败已记录）
- [ ] 关注股.md已更新
- [ ] 每日日志已写入

---

## 附录：选股引擎逻辑说明

引擎位于 `scripts/lobster_premarket_engine.py`，数据源和规则如下：

| 步骤 | 数据源 | 说明 |
|------|--------|------|
| 指数涨跌 | qt.gtimg.cn | 上证/深证/创业板实时 |
| 涨跌家数 | legulegu.com | 情绪判定核心数据 |
| 昨日涨停池 | akshare stock_zt_pool_previous_em | 1.0/2.0维度选股基础 |
| 连板池 | akshare stock_zt_pool_sub_new_em | 1.0分歧低吸基础 |
| 趋势容量池 | trading/趋势容量池.md | 3.0维度选股基础 |

### 情绪→维度→仓位（硬编码）
| 涨跌家数 | 主导 | 辅助 | 仓位上限 |
|----------|------|------|----------|
| <1500 | 1.0 | 无 | 5成 |
| 1500-2500 | 1.0 | 3.0 | 9成(3仓×3成) |
| 2500-3500 | 2.0 | 1.0 | 7成 |
| >3500 | 辅助 | 无 | 2成 |

### 各维度选股规则
- **1.0一进二**：昨日首板（连板数=1），按额排序（小优先），板块有助攻加分，取前5
- **1.0分歧低吸**：2-3连板股，按连板数+板块强度排序，排除≥4板，取前4
- **2.0板块卡位**：板块涨停≥3家，取额最大的前排股，按板块涨停数排序，取前5
- **3.0趋势低吸**：从趋势容量池选均线多头+赛道🔴的，按产业逻辑+成交额评分，取前3

### 规则迭代方式
修改引擎顶部的 `EMOTION_RULES` 字典即可调整情绪判定参数。
更复杂的规则修改直接编辑脚本中的打分函数。

---

**任务版本**：v5（新增催化日历读取）
**最后更新**：2026-05-20
