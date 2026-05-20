# 龙虾收盘复盘 — cron 任务指令（v4）

> **执行时间**：交易日 15:05
> **前置任务**：读取本日盘前选股+竞价选股+午间复盘笔记（从IMA搜索）
> **输出**：完整复盘报告（按复盘模板格式）+ 更新选股历史

---

## 步骤0：前置任务校验（必做）

```bash
python3 << 'PYEOF'
import json, datetime, sys

today = datetime.date.today().strftime('%Y-%m-%d')
errors = []

# 检查盘前候选池JSON
try:
    with open('/tmp/lobster_premarket_candidates.json') as f:
        data = json.load(f)
    if data.get('date') != today:
        errors.append(f"盘前候选池JSON日期={data.get('date')}，非今天{today}")
    else:
        print(f"✅ 盘前候选池JSON正常 (日期={today}, 情绪={data['emotion'].get('主导维度','?')})")
except FileNotFoundError:
    errors.append("盘前候选池JSON不存在 — 07:00盘前选股任务可能失败")
except Exception as e:
    errors.append(f"盘前候选池JSON读取失败: {e}")

# 检查竞价选股结果JSON
try:
    with open('/tmp/lobster_bid_result.json') as f:
        data = json.load(f)
    if data.get('date') != today:
        errors.append(f"竞价选股JSON日期={data.get('date')}，非今天{today}")
    else:
        results = data.get('results', {})
        found = sum(1 for v in results.values() if v)
        print(f"✅ 竞价选股JSON正常 (日期={today}, 选出{found}只)")
except FileNotFoundError:
    errors.append("竞价选股JSON不存在 — 09:25竞价选股任务可能失败")
except Exception as e:
    errors.append(f"竞价选股JSON读取失败: {e}")

# 检查午间复盘文件
try:
    with open(f'/tmp/lobster_midday_{today}.md') as f:
        content = f.read()
    print(f"✅ 午间复盘文件存在 ({len(content)}字节)")
except FileNotFoundError:
    errors.append("午间复盘文件不存在 — 11:30午间复盘任务可能失败")

# 检查关注股.md
try:
    with open('/Users/yuefengshen/.qclaw/workspace-1gwpiwf3hr163jz5/trading/关注股.md') as f:
        content = f.read()
    if len(content) < 50:
        errors.append("关注股.md内容过短，可能异常")
    else:
        print(f"✅ 关注股.md正常 ({len(content)}字节)")
except FileNotFoundError:
    errors.append("关注股.md不存在")

if errors:
    print(f"\n🚨 前置校验失败 ({len(errors)}个问题):")
    for e in errors:
        print(f"  - {e}")
    print(f"\n⚠️ 收盘复盘将在不完整数据下执行，结论可能不准确！")
else:
    print("\n✅ 所有前置校验通过")
PYEOF
```

## 步骤0.7：新赛道检测硬约束（必做）

> **目标**：自动识别连续2日爆发的板块，提示人工审核是否加入产业逻辑框架

```bash
python3 << 'PYEOF'
import json, akshare as ak
from datetime import datetime, timedelta
from pathlib import Path

today = datetime.now().strftime('%Y%m%d')
yday = (datetime.now() - timedelta(days=1)).strftime('%Y%m%d')
today_f = Path(f'/tmp/sector_limit_up_{today}.json')
yday_f = Path(f'/tmp/sector_limit_up_{yday}.json')

# 保存今日板块涨停数据
try:
    df = ak.stock_zt_pool_em(date=today)
    # 统计板块涨停家数（所属行业）
    board_cnt = {}
    for _, row in df.iterrows():
        board = row.get('所属行业', '未知')
        board_cnt[board] = board_cnt.get(board, 0) + 1
    with open(today_f, 'w') as f:
        json.dump({'date': today, 'board': board_cnt}, f, ensure_ascii=False)
    print(f"✅ 今日板块涨停数据已保存")
except Exception as e:
    print(f"⚠️ 保存今日数据失败: {e}")
    exit(0)

# 检测连续2日≥3家涨停
if yday_f.exists():
    with open(yday_f) as f: d1 = json.load(f)
    with open(today_f) as f: d2 = json.load(f)
    new = [b for b in d2['board'] if d2['board'][b] >= 3 and b in d1['board'] and d1['board'][b] >= 3]
    if new:
        print(f"🚨 新赛道候选（连续2日≥3家涨停）: {new}")
        framework = Path('/Users/yuefengshen/.qclaw/workspace-1gwpiwf3hr163jz5/trading/产业逻辑框架.md').read_text()
        pending = [b for b in new if b not in framework]
        if pending:
            with open('/tmp/pending_tracks.md', 'a') as f:
                for b in pending:
                    f.write(f"- [ ] {b}（{today} 连续2日≥3家涨停）\n")
            print(f"   已写入 /tmp/pending_tracks.md，下次进化任务时审核")
    else:
        print("✅ 无新赛道候选")
else:
    print(f"⚠️ 昨日数据缺失，跳过检测")
PYEOF
```

## 步骤1.6：催化日历滚动更新（必做）

> 每次收盘复盘必须更新 `trading/催化日历.md`——已兑现移归档、已落空填原因、新催化加入近期区。

```bash
# 读取今日催化日历
cat /Users/yuefengshen/.qclaw/workspace-1gwpiwf3hr163jz5/trading/催化日历.md

# 对照今日市场数据，判断是否有催化兑现/落空
# 兑现：标注✅ + 兑现日期，移入「已兑现催化归档区」
# 落空：标注❌ + 落空原因 + 对赛道影响，移入「落空催化归档区」
# 新催化：追加至「近期催化」

# 用 edit 工具修改文件（不要全文件覆盖，仅更新变化的部分）
# 更新后确认文件顶部「最后更新」日期已改为今日

# 示例兑现判断逻辑（需人工确认，不强制）：
# - 某催化事件在今日有明确的市场验证信号 → 兑现
# - 某催化预期日期已过但无任何市场反应 → 落空
# - 某赛道持续横盘且无资金关注超过10个交易日 → 评估是否将相关催化标记落空
```

> ⚡ 提示：只需关注「近期催化」区的未决事件，已在归档区的不重复处理。

---

## 步骤0.5：读取复盘模板（必做）

```bash
# 读取复盘模板，按9个章节输出
cat ~/.qclaw/workspace-1gwpiwf3hr163jz5/trading/复盘模板.md
```

---

## 步骤1：获取市场数据（实时）

```bash
python3 << 'PYEOF'
import subprocess, re, datetime, json

# 指数涨跌（腾讯接口，实时）
r1 = subprocess.run(["curl","-s","https://qt.gtimg.cn/q=sh000001,sz399001,sz399006"], capture_output=True, timeout=15)
raw1 = r1.stdout
for enc in ["gb2312","gbk","utf-8"]:
    try: txt1 = raw1.decode(enc); break
    except: continue
else: txt1 = raw1.decode("utf-8","replace")
indices = {}
for line in txt1.split(";"):
    m = re.search(r'v_(\w+)="([^"]*)"', line)
    if m:
        parts = m.group(2).split("~")
        if len(parts) > 32:
            name = parts[1]
            price = parts[3]
            pct = parts[32]
            indices[name] = f"{price}({pct}%)"
            print(f"{name}: {price} ({pct}%)")

# 涨跌家数（legulegu，实时）
r2 = subprocess.run(["curl","-s","-L","--max-time","15","-A","Mozilla/5.0","https://legulegu.com/stockdata/market-activity"], capture_output=True, text=True, timeout=20)
m2 = re.search(r'content="(2026-[^"]+)"', r2.stdout)
emotion_text = m2.group(1) if m2 else "获取失败"
print(f"\n涨跌家数: {emotion_text}")

# 解析涨跌家数数字
m_up = re.search(r'(\d+)家上涨', emotion_text)
m_down = re.search(r'(\d+)家下跌', emotion_text)
up_count = int(m_up.group(1)) if m_up else 0
down_count = int(m_down.group(1)) if m_down else 0

# 情绪判定
if up_count < 1000:
    emotion = "冰点"
elif up_count < 1500:
    emotion = "偏弱"
elif up_count < 2500:
    emotion = "正常"
elif up_count < 3500:
    emotion = "高潮"
else:
    emotion = "极度高潮"

# 维度判定
if up_count < 1500:
    dimension = "1.0"
    pos_limit = 3
elif up_count < 2500:
    dimension = "1.0+3.0"
    pos_limit = 5
elif up_count < 3500:
    dimension = "2.0+1.0"
    pos_limit = 7
else:
    dimension = "辅助"
    pos_limit = 2

print(f"情绪判定: {emotion}")
print(f"主导维度: {dimension}")
print(f"总仓位上限: {pos_limit}成")

# 保存到文件供后续使用
result = {
    "indices": indices,
    "up_count": up_count,
    "down_count": down_count,
    "emotion": emotion,
    "dimension": dimension,
    "pos_limit": pos_limit,
    "emotion_text": emotion_text
}
with open("/tmp/lobster_closing_data.json", "w") as f:
    json.dump(result, f, ensure_ascii=False, indent=2)
PYEOF
```

---

## 步骤1.5：趋势容量池自动更新（新增）

> 每日收盘后自动更新 3.0 趋势池，刷新均线/成交额/市值数据。

```bash
cd /Users/yuefengshen/.qclaw/workspace-1gwpiwf3hr163jz5
python3 scripts/lobster_trend_pool_updater.py 2>&1
python3 -c "import json; d=json.load(open('/tmp/lobster_trend_pool_update.json')); print(f'👇 入池{len(d[\"pool\"])}只 → 趋势容量池.md')"
```

**v2.1 入池硬约束复检：**

| 约束 | 阈值 |
|------|------|
| 5日均成交额 | ≥10亿 |
| 总市值 | ≥100亿 |
| 总分 | ≥35分 |

> ⚡ 此步骤失败不应阻塞收盘复盘流程。若腾讯API限流导致数据不全，记录后继续。

---

## 步骤2：获取涨停池数据（含二次验证）

```bash
python3 << 'PYEOF'
import akshare as ak, datetime, re, subprocess, json

# 今日涨停池
zt_today = ak.stock_zt_pool_em()
print("=== 今日涨停池 ===")
print(zt_today[['代码', '名称', '涨停统计', '所属行业', '涨停原因类别']].head(30).to_string())

# 统计板块涨停数
if '所属行业' in zt_today.columns:
    sector_counts = zt_today['所属行业'].value_counts().head(10)
    print("\n=== 板块涨停排名 ===")
    print(sector_counts.to_string())

# 昨日涨停今日表现（判断昨日日期）
today = datetime.date.today()
weekday = today.weekday()
if weekday == 0:  # 周一
    yesterday = today - datetime.timedelta(days=3)
else:
    yesterday = today - datetime.timedelta(days=1)

try:
    zt_prev = ak.stock_zt_pool_previous_em(date=yesterday.strftime('%Y%m%d'))
    print(f"\n=== 昨日涨停今日表现（{yesterday}）===")
    print(zt_prev[['代码', '名称', '涨跌幅', '连板数']].head(20).to_string())
except Exception as e:
    print(f"获取昨日涨停失败: {e}")

# ⚠️ 新增：涨停二次验证（必须执行）
print("\n=== 涨停二次验证 ===")

def get_zhangting_limit(代码):
    """根据代码判断涨跌幅限制"""
    if 代码.startswith('688'):  # 科创板
        return 0.2
    elif 代码.startswith('300'):  # 创业板
        return 0.2
    elif 代码.startswith('8') or 代码.startswith('4'):  # 北交所
        return 0.3
    else:
        return 0.1  # 主板

# 批量获取涨停股实时数据
zt_codes = zt_today['代码'].head(30).tolist()
if zt_codes:
    # 构造查询字符串
    query_codes = []
    for code in zt_codes:
        if code.startswith('6'):
            query_codes.append(f"sh{code}")
        else:
            query_codes.append(f"sz{code}")
    
    query = ','.join(query_codes)
    r = subprocess.run(["curl", "-s", f"https://qt.gtimg.cn/q={query}"], 
                      capture_output=True, timeout=15)
    raw = r.stdout
    for enc in ["gb2312","gbk","utf-8"]:
        try: txt = raw.decode(enc); break
        except: continue
    else: txt = raw.decode("utf-8","replace")
    
    # 解析数据
    verify_results = []
    for line in txt.split(";"):
        m = re.search(r'v_(\w+)="([^"]*)"', line)
        if m:
            parts = m.group(2).split("~")
            if len(parts) > 32:
                代码 = parts[2]
                名称 = parts[1]
                现价 = float(parts[3])
                昨收 = float(parts[4])
                涨跌幅 = float(parts[32])
                
                # 计算涨停价
                limit = get_zhangting_limit(代码)
                涨停价 = 昨收 * (1 + limit)
                
                # 判断是否真的涨停
                实际涨停 = 现价 >= 涨停价 * 0.995
                
                if 实际涨停:
                    涨停类型 = "20cm涨停" if limit >= 0.19 else "涨停"
                else:
                    涨停类型 = f"未涨停（涨幅{涨跌幅:.2f}%）"
                
                verify_results.append((名称, 代码, 涨跌幅, 涨停类型, 实际涨停))
    
    # 输出验证结果
    for 名称, 代码, 涨跌幅, 涨停类型, 实际涨停 in verify_results:
        status = "✅" if 实际涨停 else "⚠️"
        print(f"{status} {名称}({代码}): {涨跌幅:.2f}% → {涨停类型}")

print("\n验证完成")
PYEOF
```

---

## 步骤3：读取关注股（今日候选）

```bash
# 读取今日最终关注股
cat ~/.qclaw/workspace-1gwpiwf3hr163jz5/trading/关注股.md

# 或从盘前候选池JSON读取
python3 -c "import json; print(json.dumps(json.load(open('/tmp/lobster_premarket_candidates.json')), ensure_ascii=False, indent=2))"
```

---

## 步骤4：按复盘模板输出（9个章节）

> **必须严格按 `复盘模板.md` 格式输出，不得遗漏章节**

### 章节内容：

1. **情绪周期判定**：指数涨跌 + 涨跌家数 + 情绪定位
2. **连板梯队分析**：按连板数表格 + 断板分析
3. **板块轮动分析**：最强板块表格 + 产业逻辑对照
4. **昨日选股今日表现**：从关注股读取 + 逐只分析
5. **明日候选标的**：4档候选池（每档3-5只）
6. **模式审计**：按 lobster-rules.md 审计6项
7. **明日策略**：若情绪X则维度Y + 仓位Z
8. **每日进化（待办）**：记录错误 + 优化建议
9. **IMA同步**：确认同步状态

---

## 步骤5：自动更新选股历史（必须执行）

```bash
python3 << 'PYEOF'
import datetime, json, re

today = datetime.date.today().strftime('%Y-%m-%d')

# 读取今日竞价选股结果（从JSON）
try:
    with open('/tmp/lobster_bid_result.json') as f:
        bid_result = json.load(f)
except:
    bid_result = {'results': {}}

# 如果JSON不存在，从关注股.md读取
if not bid_result.get('results'):
    try:
        with open("/Users/yuefengshen/.qclaw/workspace-1gwpiwf3hr163jz5/trading/关注股.md") as f:
            watch_list = f.read()
        # 提取关注股（每档第1只）
        lines = watch_list.split('\n')
        results = {}
        for line in lines:
            if '##' in line and '一进二' in line:
                tier = '1.0一进二'
            elif '##' in line and '分歧低吸' in line:
                tier = '1.0分歧低吸'
            elif '##' in line and '板块卡位' in line:
                tier = '2.0板块卡位'
            elif '##' in line and '趋势低吸' in line:
                tier = '3.0趋势低吸'
            elif line.startswith('- ') and tier:
                # 提取股票名称和代码
                m = re.search(r'([^\(]+)\((\d{6})\)', line)
                if m:
                    results[tier] = {'name': m.group(1).strip(), 'code': m.group(2)}
        bid_result = {'results': results, 'date': today}
    except:
        pass

# 读取选股历史文件
history_file = "/Users/yuefengshen/.qclaw/workspace-1gwpiwf3hr163jz5/trading/选股历史.md"
try:
    with open(history_file) as f:
        history = f.read()
except:
    history = ""

# 检查今日是否已记录
if today in history and '竞价选股' in history:
    print(f"✅ 今日（{today}）选股历史已存在，跳过写入")
else:
    # 构造历史记录条目
    entries = []
    for tier, stock in bid_result.get('results', {}).items():
        if stock and isinstance(stock, dict):
            name = stock.get('name', '未知')
            code = stock.get('code', '000000')
            change_pct = stock.get('change_pct', 0)
            
            # 构造买入条件（简化版）
            if '一进二' in tier:
                buy_cond = f"若秒板则排板"
            elif '分歧低吸' in tier:
                buy_cond = f"若低开后企稳则低吸"
            elif '板块卡位' in tier:
                buy_cond = f"若回踩5日线不破则低吸"
            elif '趋势低吸' in tier:
                buy_cond = f"若回踩5日线不破则低吸"
            else:
                buy_cond = "待确定"
            
            entries.append(f"| {today} | 竞价选股 | {name}({code}) | {buy_cond} | 待验证 | 待验证 | - | - |")
    
    # 找到表格位置并追加
    if entries:
        # 找到表格最后一行
        lines = history.split('\n')
        insert_pos = -1
        for i, line in enumerate(lines):
            if line.startswith('|') and '待验证' in line:
                insert_pos = i
            elif line.startswith('|') and '日期' in line:
                # 找到表头后的分隔行
                if i+1 < len(lines) and lines[i+1].startswith('|') and '---' in lines[i+1]:
                    insert_pos = i + 1
        
        # 如果找不到合适位置，追加到表格最后
        if insert_pos == -1:
            # 在"## 准确率统计"之前插入
            for i, line in enumerate(lines):
                if '准确率统计' in line:
                    insert_pos = i
                    break
            
            if insert_pos > 0:
                lines.insert(insert_pos, '\n'.join(entries) + '\n')
            else:
                # 追加到文件末尾
                history += '\n'.join(entries) + '\n'
        else:
            # 在找到的位置后追加
            lines.insert(insert_pos + 1, '\n'.join(entries) + '\n')
            history = '\n'.join(lines)
        
        # 写入文件
        with open(history_file, 'w') as f:
            f.write(history)
        
        print(f"✅ 已追加写入选股历史.md（{len(entries)}条记录）")
        for entry in entries:
            print(f"  - {entry}")
    else:
        print("⚠️ 未找到今日选股结果")
PYEOF
```

---

## 步骤6：IMA同步

```bash
# 将完整复盘写入临时文件
OUTPUT="/tmp/lobster_closing_$(date +%Y-%m-%d).md"

# （agent会将复盘内容写入此文件）

# 调用IMA同步脚本（含重试）
bash ~/.qclaw/workspace-1gwpiwf3hr163jz5/scripts/ima_sync.sh "$OUTPUT" "龙虾收盘复盘 $(date +%Y-%m-%d)"

# 移入每日复盘文件夹（可选）
# curl -X POST "https://ima.qq.com/openapi/wiki/v1/move_knowledge" ...
```

---

## 步骤7：发送消息给用户

```bash
# 发送简洁版复盘摘要
# message工具发送到元宝
```

---

## 步骤8：结构化复盘数据导出（新增）

将今日复盘关键数据追加写入结构化 Excel 文件 `trading/复盘数据库.xlsx`。

**操作**：使用 `xlsx` 技能创建/追加 Excel 文件。

1. 读取 xlsx 技能（路径：`~/.qclaw/skills/xlsx/SKILL.md`）
2. 用 openpyxl（技能依赖）执行以下 Python 脚本：

```python
import openpyxl
from datetime import date
import json, os

FILE = '/Users/yuefengshen/.qclaw/workspace-1gwpiwf3hr163jz5/trading/复盘数据库.xlsx'
WS_PATH = '/Users/yuefengshen/.qclaw/workspace-1gwpiwf3hr163jz5'

headers = ['日期','维度','关注标的','代码','开盘价','收盘价','涨幅%','打分','竞价量比','涨停数','涨跌家数','情绪判定','命中']

today = date.today().strftime('%Y-%m-%d')

if os.path.exists(FILE):
    wb = openpyxl.load_workbook(FILE)
    ws = wb.active
else:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = '复盘记录'
    ws.append(headers)
    # 格式化表头
    from openpyxl.styles import Font, PatternFill
    for cell in ws[1]:
        cell.font = Font(bold=True)
        cell.fill = PatternFill(start_color='4472C4', end_color='4472C4', fill_type='solid')
        cell.font = Font(bold=True, color='FFFFFF')

# 去重检查：如果今日已有记录则更新，否则追加
existing_row = None
for row in ws.iter_rows(min_row=2, max_col=1):
    if row[0].value == today:
        existing_row = row[0].row
        break

# 从各数据源收集今日数据
row_data = [today]

# 维度（从 trading-state.json 读取）
try:
    with open(f'{WS_PATH}/trading/trading-state.json') as f:
        state = json.load(f)
    row_data.append(state.get('dimension', ''))
except:
    row_data.append('')

# 关注标的（从 trading/关注股.md 提取第一行标的名和代码）
try:
    with open(f'{WS_PATH}/trading/关注股.md') as f:
        content = f.read()
    lines = [l for l in content.split('\n') if '|' in l and not l.strip().startswith('|--')]
    if len(lines) > 2:
        cells = [c.strip() for c in lines[2].split('|')]
        row_data.extend([cells[0] if len(cells)>0 else '', cells[1] if len(cells)>1 else ''])
    else:
        row_data.extend(['',''])
except:
    row_data.extend(['',''])

# 行情数据（留空由收盘任务填入）
row_data.extend(['','','','','','',''])

# 命中判定
row_data.append('')

if existing_row:
    for i, val in enumerate(row_data):
        ws.cell(row=existing_row, column=i+1, value=val)
    print(f'✅ 已更新第{existing_row}行（{today}）')
else:
    ws.append(row_data)
    print(f'✅ 已追加新行（{today}）')

wb.save(FILE)
```

3. 如果文件不存在会自动创建（含表头格式化）
4. 如果今日已有记录（同一日期），更新而非重复追加

> ⚡ 此步骤失败不应阻塞复盘流程，记录错误后继续。

---

## ❌ 错误处理与实时告警

**任何步骤失败，立即发送告警（不等待晚间修复）：**

| 步骤 | 失败表现 | 告警内容 |
|------|---------|----------|
| 读取复盘模板 | 文件不存在 | 【CRON_CLOSING_TASK 告警】复盘模板丢失 |
| 获取市场数据 | curl返回空 | 【CRON_CLOSING_TASK 告警】无法获取市场数据 |
| IMA同步 | 返回非0 | 【CRON_CLOSING_TASK 告警】IMA同步失败 |

**告警方式**：调用 `message` 工具发送到 IMA 知识库「ai自动选股」

---

## ✅ 完成标志

- [ ] 已按复盘模板输出9个章节
- [ ] 已更新 `trading/选股历史.md`
- [ ] **已更新 `trading/催化日历.md`**（滚动归档+新催化追加）
- [ ] 已同步IMA知识库
- [ ] 已发送消息给用户
- [ ] 已写入 `memory/YYYY-MM-DD.md`
- [ ] 已追加 `trading/复盘数据库.xlsx`

---

**任务版本**：v5（新增催化日历滚动更新）
**最后更新**：2026-05-20
