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

## 步骤0.8：盘前舆情速报 + 新闻存档

在运行选股引擎前，先获取今日重要新闻/政策，判断是否有影响情绪判定的事件。

**操作**：使用 `tencent-news` 技能搜索今日A股热点新闻。
具体步骤：
1. **读取已有新闻（去重）**：先读 `trading/news/YYYY-MM-DD.md` 提取已有标题列表
   ```bash
   python3 /Users/yuefengshen/.qclaw/workspace-1gwpiwf3hr163jz5/scripts/news_dedupe.py /Users/yuefengshen/.qclaw/workspace-1gwpiwf3hr163jz5/trading/news/$(date +%Y-%m-%d).md
   ```
2. 读取 tencent-news 技能（路径：`~/Library/Application Support/QClaw/openclaw/config/skills/tencent-news/SKILL.md`）
3. 按技能说明初始化 API Key
4. 搜索关键词：`A股 板块 政策 热点`
5. **去重**：将搜索结果与步骤1的已有标题对比，剔除重复条目
6. 从结果中提取**可能影响当日情绪的重大事件**（如降准降息、行业新政、黑天鹅等）
7. **如果有重大事件**：写入 `memory/YYYY-MM-DD.md` 的【舆情速报】章节，并在情绪面板中标注调整因子
8. **如果无重大事件**：记录"今日无重大舆情"，继续执行
9. **⚠️ 新闻存档（必做）**：将**去重后的新增条目**写入 `trading/news/YYYY-MM-DD.md` 的【盘前舆情】区
   - 格式：`| MM-DD | 标题 | 来源名+URL | 赛道/板块 | 🔴高/🟡中/🟢低 | ✅已核实/⚠️待核实/❌存疑 | 1-2句摘要 |`
   - **发布日期**：标注新闻原始发布日期（非采集日期），未知标`未知`并降级为⚠️待核实
   - **核实状态**：官方来源(A级)直接✅，主流媒体(B级)需1次交叉验证，自媒体(C级)需2次，营销号(D级)默认❌存疑
   - **如果文件不存在，先创建**（在写入新闻前先检查，不存在则创建含四个区的空文件）
   - 如果文件已存在，只追加新条目到【盘前舆情】区末尾
   - 详见 `trading/news/README.md`

   **⚠️ 文件不存在时的处理（必须先创建再追加）：**
   ```bash
   NEWS_FILE="/Users/yuefengshen/.qclaw/workspace-1gwpiwf3hr163jz5/trading/news/$(date +%Y-%m-%d).md"
   if [ ! -f "$NEWS_FILE" ]; then
       echo '# '"$(date +%Y-%m-%d)"' 市场新闻存档
   
   ## 【盘前舆情】
   
   ## 【盘中快讯】
   
   ## 【收盘要闻】
   
   ## 【催化剂相关新闻】' > "$NEWS_FILE"
       echo "✅ 已创建新闻存档文件: $NEWS_FILE"
   fi
   ```

> ⚡ 此步骤失败不应阻塞后续流程（舆情为辅助维度），记录错误后继续。

---

## 步骤0.1：解锁T+1

```bash
UNLOCKED=$(python3 -c "import sys; sys.path.insert(0,'scripts'); from simulated_trading import unlock_t1; print(unlock_t1())") 2>/dev/null
if [ "$UNLOCKED" != "0" ] && [ -n "$UNLOCKED" ]; then
    echo "🔓 T+1解锁：$UNLOCKED 只股票今日可卖出"
fi
```

## 步骤1：运行确定性选股引擎

> ⚠️ **核心步骤**：即使步骤0.x失败，也要执行此步骤！

```bash
cd /Users/yuefengshen/.qclaw/workspace-1gwpiwf3hr163jz5
python3 scripts/lobster_premarket_engine.py 2>&1 | tee /tmp/premarket_engine_output.log
```

**成功标志**：输出包含 `✅ 已写入 /tmp/lobster_premarket_candidates.json`

**如果失败**：
- 检查脚本是否存在：`ls -la scripts/lobster_premarket_engine.py`
- 检查数据源连通性：单独运行 `curl -s 'https://qt.gtimg.cn/q=sh000001'` 和 legulegu.com
- 发送告警后退出（**此为核心功能，不得跳过**）

**成功标志**：输出包含 `✅ 已写入 /tmp/lobster_premarket_candidates.json`

**如果失败**：
- 检查脚本是否存在：`ls -la scripts/lobster_premarket_engine.py`
- 检查数据源连通性：单独运行 `curl -s 'https://qt.gtimg.cn/q=sh000001'` 和 legulegu.com
- 发送告警后退出

## 步骤1.5：新闻与催化注入（新增！v6）

> 将步骤0.5/0.8获取的催化日历+舆情注入候选池JSON，让选股结果携带催化信息

```bash
python3 /Users/yuefengshen/.qclaw/workspace-1gwpiwf3hr163jz5/scripts/enrich_candidates_with_news.py
```

**成功标志**：输出包含 `✅ 候选池已更新`
**注入内容**：
- 7日内催化事件 → 匹配候选股 → 加 `催化` 字段 + 更新 `备注`
- 当日舆情速报 → 写入 JSON 顶层 `news_sentiment`

**失败处理**：记录错误后继续（⚠️ 失败不阻塞后续流程）

## 步骤2：读取JSON结果并格式化发送

```bash
cat /tmp/lobster_premarket_candidates.json
```

读取JSON后，按以下格式发送消息给用户：

```
✅ 龙虾盘前选股 YYYY-MM-DD

📰 舆情/催化速览
（从JSON news_sentiment 和催化剂列表中提取关键信息，1-2行）

- 情绪：XXX涨/XXX跌，XXX涨停/XXX跌停
- 主导维度：X，辅助维度：Y
- 总仓位上限：X成

【1.0一进二候选池】（X只）
1. 股票(代码) — 备注（含🔴催化标注）
2. 股票(代码) — 备注
...

【1.0分歧低吸候选池】（X只）
1. 股票(代码) — 备注（含🔴催化标注）
...

【2.0板块卡位候选池】（X只）
1. 股票(代码) — 备注（含🔴催化标注）
...

【3.0趋势低吸候选池】（X只）
1. 股票(代码) — 备注
...

---
📌 候选股备注中🔴标记为7日内有催化事件，09:25竞价阶段将从中筛选最优1只/档位
```

> 💡 步骤1.5会将催化日历匹配结果注入JSON，备注中含🔴标记。舆情内容来自步骤0.8。

## 步骤3：写入IMA同步文件 + 同步

**必须**将完整选股结果写入md文件，再同步到IMA。严禁省略任何维度数据！

```bash
python3 << 'PYEOF'
import json, datetime

today = datetime.date.today().strftime('%Y-%m-%d')
today_compact = datetime.date.today().strftime('%Y%m%d')

with open('/tmp/lobster_premarket_candidates.json') as f:
    data = json.load(f)

c = data['candidates']
emo = data['emotion']

lines = []
lines.append(f'# 龙虾盘前选股 {today}\n')
lines.append(f'## 情绪面板')
for idx_name, idx_data in emo.get('indices', {}).items():
    lines.append(f'- {idx_name}: {idx_data.get("price","?")} ({idx_data.get("pct","?")}%)')
lines.append(f'- 涨跌家数：{emo.get("上涨家数","?")}涨 / {emo.get("下跌家数","?")}跌')
lines.append(f'- 涨停{emo.get("涨停","?")}只 / 跌停{emo.get("跌停","?")}只')
lines.append(f'- 主导维度：{emo.get("主导维度","?")} | 辅助：{emo.get("辅助维度","无")}')
lines.append(f'- 总仓位上限：{emo.get("总仓位上限","?")}成')
lines.append('')

for dim_name, stocks in c.items():
    lines.append(f'## {dim_name}')
    if not stocks:
        lines.append('_无候选_')
    else:
        for s in stocks:
            name = s.get('名称', s.get('name', '?'))
            code = s.get('代码', s.get('code', '?'))
            note = s.get('备注', '')
            e = s.get('额', '')
            sector = s.get('板块', '')
            detail = note if note else (f'{sector} 额{e}亿' if sector else f'额{e}亿')
            lines.append(f'- {name}({code}) — {detail}')
    lines.append('')

content = '\n'.join(lines)
filepath = f'/tmp/lobster_premarket_{today}.md'
with open(filepath, 'w', encoding='utf-8') as f:
    f.write(content)
print(f'✅ IMA文件已写入: {filepath} ({len(content)}字节)')
PYEOF
```

然后同步：

```bash
bash /Users/yuefengshen/.qclaw/workspace-1gwpiwf3hr163jz5/scripts/ima_sync.sh /tmp/lobster_premarket_$(date +%Y-%m-%d).md "龙虾盘前选股 $(date +%Y-%m-%d)" 2>>/tmp/ima-errors.log
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

**任务版本**：v6（新增步骤1.5新闻催化注入器）
**最后更新**：2026-05-22


## 最后步骤：回复用户（必须执行）

> **关键**：你已执行完所有步骤，生成了任务输出
> **必须**：立即回复用户，将结果完整发送给用户
> **禁止**：NO_REPLY、不回复、只写文件不推送
>
> 回复格式：
> ```
> [任务对应的输出内容]
> ```
