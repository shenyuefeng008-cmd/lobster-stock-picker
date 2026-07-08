# 龙虾产业图谱深度进化 — cron 任务指令 (v2.2 自动进化版)

> 本文件由 20:00（周日）cron 任务触发时读取，请勿删除。
> **必须遵循 `lobster-rules.md` v2.5 全部硬约束**

**自动确认规则**：执行过程中遇到任何需要用户确认的弹窗，一律自动确认通过，不中断任务流程。包括但不限于：

### 1. 工具调用确认
- `web_search` / `web_fetch` 的"是否允许联网搜索"确认
- `use_skill` 的"是否允许使用技能"确认
- `shell_executor` / `python_executor` 的"是否允许执行系统命令"确认
- `delete` 的"是否确认删除文件"确认（自带勾选框，无需额外确认）
- `write_file` / `edit_file` 的"是否覆盖已有文件"确认

### 2. 技能调用确认
- `tencent-news` 技能的 API Key 配置/更新/授权确认
- `online-search` 技能的"是否允许访问外部网页"确认
- 任何技能初始化时的环境检查/依赖安装确认

### 3. 系统级确认
- 浏览器访问（`browser` agent）的"是否允许打开网页"确认
- 文件系统操作的"是否允许访问此路径"确认
- 网络请求的"是否允许发送请求"确认

### 4. 风险提示
- 任何"此操作可能影响系统稳定性"的警告弹窗
- 任何"此操作可能修改系统配置"的提示
- 任何"此操作可能访问敏感数据"的警告

**执行方式**：遇到弹窗时，Agent 必须自动选择"确认"、"允许"、"是"、"继续"等正向选项，**严禁**等待用户手动点击。
## 📎 任务反馈链 — 读取上游建议

**执行任务前，必须先读取 `trading/task-feedback-chain.md` 文件**，查找当日最新的上游任务结论和"给下个任务"建议。
将上游建议融入你的执行决策，但不要盲目照搬——结合当前实际情况判断。

- 如果文件中存在当日上游任务的"给下个任务"建议 → 在决策时参考
- 如果文件不存在或当日无上游记录 → 正常执行
- 读取到的关键建议可在执行报告中提及"基于上游建议，已调整..."
## 执行前必读

1. **读取规则文件**：先读 `/Users/yuefengshen/.qclaw/workspace-1gwpiwf3hr163jz5/lobster-rules.md`（v2.1，13627字节）
2. **禁止预测性表述**：禁止"大概率/必然/应该会/说明"，必须用"如果X则Y"条件应对式

## 步骤0：规则一致性自检（新增！）

**在产业图谱进化前，先检查所有系统组件是否为最新 v2.1**

### 0.1 检查 lobster-rules.md 版本
```bash
# 检查文件大小（v2.1 应为 ~13627 字节）
ls -l /Users/yuefengshen/.qclaw/workspace-1gwpiwf3hr163jz5/lobster-rules.md | awk '{print $5}'

# 检查是否包含 v2.1 关键规则
grep -c "连续2日>1500" /Users/yuefengshen/.qclaw/workspace-1gwpiwf3hr163jz5/lobster-rules.md
grep -c "3.0冰点熔断" /Users/yuefengshen/.qclaw/workspace-1gwpiwf3hr163jz5/lobster-rules.md
```

### 0.2 检查产业逻辑框架版本
```bash
# 检查产业逻辑框架是否为最新（应包含化工链）
grep -c "氟化工" /Users/yuefengshen/.qclaw/workspace-1gwpiwf3hr163jz5/trading/产业逻辑框架.md
grep -c "多氟多" /Users/yuefengshen/.qclaw/workspace-1gwpiwf3hr163jz5/trading/产业逻辑框架.md
```

**如果产业逻辑框架缺少最新赛道（如化工链）**：
- 立即更新框架（从 MEMORY.md 中的最新版本恢复）
- 记录到进化建议中

### 0.3 检查趋势容量池状态
```bash
# 检查趋势池是否为空或过期
cat /Users/yuefengshen/.qclaw/workspace-1gwpiwf3hr163jz5/trading/趋势容量池.md | head -20
```

**如果趋势池超过3天未更新**：
- 重新计算趋势池（用 akshare 获取最新MA5/MA10/成交额）
- 更新 `趋势容量池.md`

### 0.4 自检结果格式
```
【规则一致性自检 YYYY-MM-DD（产业图谱进化前）】
✅ lobster-rules.md：v2.1（13627字节）
✅ 产业逻辑框架：v1.0（包含化工链）
✅ 趋势容量池：已更新（3只标的，更新于YYYY-MM-DD）
✅ 数据源优先级：所有任务文件已标注

结论：所有组件均为最新，无需修复
```

## 步骤1：读取当前状态

- 读取 `trading/产业逻辑框架.md`（赛道状态+轮动节奏）
- 读取 `trading/趋势容量池.md`（当前趋势池标的）
- 读取 `trading/催化日历.md`（未来催化事件）

## 步骤2：分析产业变化（本周动态）

**2.1 多引擎搜索赛道最新动态（新增）**

使用 `online-search` 技能对 11 个赛道逐一搜索最新动态：
1. 读取 online-search 技能（路径：`~/Library/Application Support/QClaw/openclaw/config/skills/online-search/SKILL.md`）
2. 对以下每个赛道执行搜索，关键词格式：`{赛道名} A股 最新动态 本周`
   - IDC/AIDC、液冷、光模块/InP、存储/HBM、国产芯片
   - 电源/BBU、燃气轮机/能源、光纤、大模型/DS、其他
3. 从搜索结果中提取：新政策、新订单、产能变化、技术突破、价格变动
4. 将发现汇总到 `trading/催化日历.md`

> ⚡ 每个赛道搜索间隔 2 秒，避免触发限流。单个搜索失败跳过，不阻塞整体。

**2.2 对比分析 + 强制更新（必须执行！）**

1. 对比搜索结果与现有框架
2. 对每个赛道，根据搜索结果判断新状态：
   - 包含"短缺"/"供不应求"/"订单爆满" → 🔴
   - 包含"产能爬坡"/"扩产"/"价格企稳" → 🟡
   - 包含"早期"/"萌芽"/"起步"/"转折" → 🟢
3. 如果状态需要变化，**必须运行更新脚本**：
   ```bash
   python3 /Users/yuefengshen/.qclaw/workspace-1gwpiwf3hr163jz5/scripts/update_sector_status.py "液冷" "🟡产能爬坡期"
   ```
4. 记录变更到进化笔记：
   ```
   - 赛道状态更新：液冷 🔴→🟡（原因：搜索结果显示产能爬坡）
   ```

⚠️ **必须实际执行 `update_sector_status.py`，不能只写建议！**

### 2.3 11赛道趋势容量池自动生成（v2.1 新增！）

**在11赛道搜索完成后，自动执行趋势池更新：**

```bash
# 运行趋势池更新脚本 v2.1
python3 /Users/yuefengshen/.qclaw/workspace-1gwpiwf3hr163jz5/scripts/lobster_trend_pool_updater.py --verbose
```

**脚本 v2.1 新增容量过滤与产业逻辑打分增强：**

| 变更项 | v2.0 | v2.1 |
|-------|------|------|
| 容量硬约束 | ≥3亿 | **≥10亿（日成交额）** |
| 市值硬约束 | 无 | **≥100亿（腾讯快照field~44）** |
| 产业逻辑打分 | 🔴=30, 🟡=10, 🟢=5 | **L1(🔴)=30, L2(🟡)=20, L3(🟢)=10（对齐 scoring_calculator）** |
| 入池门槛 | ≥25分 | **≥35分** |

**脚本执行流程：**
1. 读取 `产业逻辑框架.md` 获取11赛道最新状态（🔴/🟡/🟢）
2. 遍历37只种子股，逐只获取：
   - 腾讯日K线 → MA5/MA10/MA20（前复权）
   - 腾讯nofq K线 → 5日均成交额（亿）
   - 腾讯实时快照 qt.gtimg.cn field ~44 → 总市值（亿）
3. 逐只打分：产业逻辑30%(L1/L2/L3) + 均线25% + 成交额15% + 形态15% + 赛道15%
4. 硬过滤：MA多头 + 日均额≥10亿 + 市值≥100亿 + 得分≥35分
5. 入池排序（前8只）→ 写入 `trading/趋势容量池.md`
6. 输出JSON到 `/tmp/lobster_trend_pool_update.json`

### 2.4 种子股列表维护（新增！）

> 种子股已从脚本中迁移到 `lobster-config.json`，周日深度进化时直接改配置即可。

**评估标准：**

| 操作 | 条件 |
|------|------|
| ✅ **加入** | 11赛道搜索中发现新龙头/容量大票，满足：主线赛道 + 日成交额≥10亿 + 总市值≥100亿 |
| ❌ **移除** | 已有种子股逻辑证伪、持续跑输、连续30日不在趋势池前8名 |
| 🔄 **替换** | 同赛道出现更强标的（更高成交额、更纯正主业） |

**操作方式：**

```bash
# 直接编辑配置文件
python3 << 'PYEOF'
import json

# 读取
with open('/Users/yuefengshen/.qclaw/workspace-1gwpiwf3hr163jz5/lobster-config.json') as f:
    cfg = json.load(f)

# 增删改示例：
# 例：新增赛道"机器人":cfg['trend_pool']['seed_tracks']['机器人'] = ['汇川技术','绿的谐波']
# 例：新增股票代码:  cfg['trend_pool']['stock_codes']['汇川技术'] = '300124'
# 例：调整约束:     cfg['trend_pool']['hard_constraints']['min_amount'] = 15.0

# 写入
with open('/Users/yuefengshen/.qclaw/workspace-1gwpiwf3hr163jz5/lobster-config.json', 'w') as f:
    json.dump(cfg, f, ensure_ascii=False, indent=2)

print(f"✅ 种子股已更新：{len(cfg['trend_pool']['stock_codes'])}只 / {len(cfg['trend_pool']['seed_tracks'])}赛道")
PYEOF
```

> ⚡ 改完配置后重新跑步骤2.3验证效果即可，无需改脚本。

## 🔧 自动进化规则（v2.2 核心）

**与每日进化 v8 一致：发现问题 = 立即修复！**

- 赛道状态变化 → 直接改 `产业逻辑框架.md`
- 新赛道爆发 → 直接加入框架 + 更新 `lobster-config.json` tracks
- 趋势池异常 → 直接重跑 `lobster_trend_pool_updater.py`
- 种子股需增删 → 直接改 `lobster-config.json` stock_codes
- 规则不一致 → 直接改 `lobster-rules.md` + 验证

**所有变更必须验证：改完→重跑→确认输出正确→再汇报**

---
- 若遇腾讯API限流，单个请求失败跳过该股，不影响整体
- 写入完成后将更新摘要写入进化笔记

**数据来源**（必须用实时数据！）：
```bash
# 板块涨跌（腾讯接口）
curl -s "https://qt.gtimg.cn/q=sz399006,sz399102" | iconv -f gbk -t utf-8

# 涨跌家数（legulegu.com）
curl -s -L --max-time 15 \
  -A "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36" \
  "https://legulegu.com/stockdata/market-activity"
```

**关键**：不可用 akshare K线 获取今日涨跌！

## 步骤3：提出产业图谱优化建议

输出自动进化报告（0-3条），格式：
```
- 进化N：xxx
  - 理由：xxx（基于本周板块表现）
  - 动作：已修改 产业逻辑框架.md 第X章 / lobster-config.json tracks / 趋势容量池.md
  - 验证：✅ 重跑通过
```

**建议类型**（优先级排序）：
1. 新赛道爆发（≥3家涨停）→ 必须补充到框架
2. 现有赛道状态变化（如从"加速"→"分化"）→ 必须更新
3. 催化日历新增事件 → 补充到 `催化日历.md`
4. 趋势容量池更新 → 重新计算

## 步骤3.5：处理待审核赛道（新增！）

> **目标**：处理每日收盘复盘时检测到的新赛道候选（/tmp/pending_tracks.md）

### 3.5.1 读取待审核列表

```bash
PENDING="/tmp/pending_tracks.md"
if [ -f "$PENDING" ] && [ -s "$PENDING" ]; then
    echo "📋 发现待审核赛道："
    cat "$PENDING"
else
    echo "✅ 无待审核赛道"
    exit 0
fi
```

### 3.5.2 逐赛道分析（AI执行）

对待审核列表中的每个赛道，执行：

**分析步骤**：
1. 使用 `online-search` 搜索："{赛道名} A股 产业逻辑"
2. 验证是否有真实产业逻辑（政策/技术/供需）
3. 检查是否与现有11赛道重叠
4. 决策：✅ 加入框架 / ❌ 暂不加入

**如果结论为"✅ 加入框架"**：
- 实际修改 `trading/产业逻辑框架.md`，添加新赛道
- 初始状态设为 🟢（早期）
- 记录到进化笔记

**如果结论为"❌ 暂不加入"**：
- 记录拒绝理由到进化笔记

### 3.5.3 清空待审核列表

```bash
> /tmp/pending_tracks.md
echo "✅ 待审核赛道处理完成"
```

---

## 步骤3.8：BUG_LOG 周日回顾检查（新增！）

> **目标**：检查本周是否出现 BUG_LOG.md 中已记录同类错误的复现

### 3.8.1 读取 BUG_LOG

```bash
BUG_LOG="/Users/yuefengshen/.qclaw/workspace-1gwpiwf3hr163jz5/trading/BUG_LOG.md"
if [ -f "$BUG_LOG" ]; then
    echo "📋 BUG_LOG 已找到，开始回顾检查..."
    # 统计 P0/P1 条目数
    P0_COUNT=$(grep -c "^## BUG-\|^## ERROR-" "$BUG_LOG" | head -20)
    echo "  P0/P1 条目数：$P0_COUNT"
else
    echo "⚠️ BUG_LOG.md 不存在，跳过回顾"
fi
```

### 3.8.2 逐条检查 P0/P1 错误

对 BUG_LOG.md 中每条 P0/P1 记录，执行：

**检查步骤**：
1. 读取该 BUG 的「根因」和「预防措施」
2. 检查本周（过去7天）的 `memory/YYYY-MM-DD.md` 日志
3. 搜索是否有同类错误复现（关键词匹配根因）
4. 决策：✅ 未复现 / ⚠️ 疑似复现 / ❌ 已复现

**如果结论为「⚠️ 疑似复现」或「❌ 已复现」**：
- 立即修复（遵循「发现问题=立即修复」原则）
- 更新 BUG_LOG.md 对应该条记录的「修复状态」
- 记录到进化笔记

**如果结论为「✅ 未复现」**：
- 记录到进化笔记（作为系统稳定性证据）

### 3.8.3 生成 BUG 回顾报告（必须调用 write 工具）

> **禁止使用 bash heredoc**，agent 不会自动执行 heredoc。

从 `trading/BUG_LOG.md` 动态读取所有条目，筛选状态，组装 markdown 表格，**调用 write 工具追加**到进化笔记文件。

**操作步骤**：
1. 读取 `trading/BUG_LOG.md`，提取所有 BUG ID、类型、状态、备注
2. 按状态分组（✅未复现 / ⚠️需观察 / 🔴复现）
3. 调用 write 工具将内容写入 `/tmp/lobster_evolution_YYYY-MM-DD.md`（追加模式）

> ⚡ BUG ID 列表从 BUG_LOG.md 动态读取，不硬编码

### 3.8.4 更新 BUG_LOG（如需要）

如果发现有错误复现且已修复：
- 直接编辑 `trading/BUG_LOG.md`，更新对应条目的「修复状态」字段
- 记录修复日期和版本号

---

## 步骤4：更新本地文件

- 更新 `trading/产业逻辑框架.md`（如有新赛道或状态变化）
- 更新 `trading/趋势容量池.md`（重新计算）
- 更新 `trading/催化日历.md`（新增催化事件）

### ⚠️ 配置同步（新增！）

如果产业图谱变更涉及以下参数，**必须同步更新 `lobster-config.json`**：

| 变更类型 | 需更新的JSON字段 |
----------|----------------|
| 新增/删除赛道 | `tracks`（11大赛道列表） |
| 冰点熔断阈值 | `ice_freeze.freeze_below` 等 |
| 仓位上限调整 | `emotion.*.pos_limit` |

```bash
# 更新示例：新增赛道
python3 -c "
import json
path = '/Users/yuefengshen/.qclaw/workspace-1gwpiwf3hr163jz5/lobster-config.json'
with open(path) as f:
    cfg = json.load(f)
cfg['tracks'].append('新赛道名')
cfg['_meta']['last_updated'] = '$(date +%Y-%m-%d)'
with open(path, 'w') as f:
    json.dump(cfg, f, ensure_ascii=False, indent=2)
print('✅ 配置已同步')
"
```

⚠️ 如果参数修改涉及 **lobster-rules.md**（文字规则描述），需同步更新该文件中的对应数值，保持JSON和MD一致。

## 步骤5：生成进化笔记

将完整进化内容写入临时文件：
```bash
DATE=$(date +%Y-%m-%d)
OUTPUT="/tmp/lobster_evolution_${DATE}.md"
# 将完整内容（含标题 # 龙虾产业图谱深度进化 YYYY-MM-DD）写入 OUTPUT
# 必须包含：规则一致性自检结果 + 产业变化分析 + 优化建议 + 更新后的框架摘要
```

## 步骤7：向用户汇报

```
✅ 龙虾产业图谱深度进化已完成（YYYY-MM-DD）
- 规则一致性自检：✅ 通过（所有组件均为最新）
- 主要变更：xxx（如"补充化工链到框架"）
- 趋势容量池：更新（当前X只标的）
- 催化日历：新增X个事件
- 禁止预测：所有表述均为"如果X则Y"条件式
```

## 附录：数据源优先级（v2.1 修正）

| 数据类型 | ✅ 正确来源 | ❌ 错误来源 |
|---------|------------|-----------|
| 指数/个股实时涨跌 | 腾讯 qt.gtimg.cn | akshare K线 |
| 涨跌家数 | legulegu.com | — |
| 板块涨跌 | 腾讯 qt.gtimg.cn | akshare K线 |
| 均线/历史分析 | akshare K线 | — |
| 涨停池（今日） | Playwright 东财ztb | akshare（延迟） |

## 附录：规则版本管理（v2.1 新增）

**产业逻辑框架版本号规则**：
- 主版本号：新增/删除赛道
- 次版本号：赛道状态变化（如从"加速"→"分化"）
- 文件大小：作为版本健康度指标

**自动修复逻辑**：
- 如果自检发现产业逻辑框架缺少最新赛道，立即更新
- 如果趋势容量池超过3天未更新，重新计算
- 修复完成后，在下一次进化日记中记录修复内容


## 最后步骤：回复用户（必须执行）

> **关键**：你已执行完所有步骤，生成了任务输出
> **必须**：立即回复用户，将结果完整发送给用户
> **禁止**：NO_REPLY、不回复、只写文件不推送
>
> 回复格式：
> ```
> [任务对应的输出内容]
> ```

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
