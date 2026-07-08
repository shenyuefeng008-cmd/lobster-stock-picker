# 龙虾竞价选股 — cron 任务指令（v9 完整闭环版）

> **执行时间**：交易日 09:25
> **核心任务**：读取盘前候选池 → Python硬过滤 → 更新关注股 + 发送消息

**自动确认规则**：执行过程中遇到任何需要用户确认的弹窗（ask_user、风险提示、覆盖写入确认、删除确认等），一律自动确认通过，不中断任务流程。
## 📎 任务反馈链 — 读取上游建议

**执行任务前，必须先读取 `trading/task-feedback-chain.md` 文件**，查找当日最新的上游任务结论和"给下个任务"建议。
将上游建议融入你的执行决策，但不要盲目照搬——结合当前实际情况判断。

- 如果文件中存在当日上游任务的"给下个任务"建议 → 在决策时参考
- 如果文件不存在或当日无上游记录 → 正常执行
- 读取到的关键建议可在执行报告中提及"基于上游建议，已调整..."
---

## 步骤1：读取盘前候选池，写入 `/tmp/lobster_bid_input.json`

```python
import json, subprocess

# 读取盘前候选池
with open('/tmp/lobster_premarket_candidates.json') as f:
    data = json.load(f)

# 获取所有候选股代码
codes = []
for tier in data['candidates'].values():
    for stock in tier:
        code = stock['代码']
        codes.append(('sh' + code) if code.startswith('6') else ('sz' + code))

# 获取竞价数据
q_str = ','.join(codes)
cmd = f"curl -s 'https://qt.gtimg.cn/q={q_str}' | iconv -f gbk -t utf-8"
result = subprocess.run(["bash", "-c", cmd], capture_output=True, text=True, timeout=15)

# 写入输入文件
output = {
    'date': data['date'],
    'emotion': data['emotion'],
    'candidates': data['candidates'],
    'bidding_raw': result.stdout
}
with open('/tmp/lobster_bid_input.json', 'w') as f:
    json.dump(output, f, ensure_ascii=False, indent=2)

print("✅ 输入文件已写入 /tmp/lobster_bid_input.json")
```

---

## 步骤2：运行Python过滤脚本

```bash
python3 /Users/yuefengshen/.qclaw/workspace-1gwpiwf3hr163jz5/scripts/lobster_bid_filter_v2.py
```

---

## 步骤3：更新关注股.md（关键步骤！）

```python
import json, datetime

# 读取过滤结果
with open('/tmp/lobster_bid_result.json') as f:
    result = json.load(f)

# 构造关注股内容
today = datetime.date.today().strftime('%Y-%m-%d')
content = f"""# 🎯 关注股（{today} 竞价更新）

"""

for tier_name, best in result['results'].items():
    if best:
        content += f"""## {tier_name}
- {best['name']}({best['code']}) — 竞价高开{best['change_pct']}%，竞量{best['volume']}手
  - 买入条件：若回踩5日线不破 → 低吸

"""
    else:
        content += f"""## {tier_name}
- ⚠️ 无符合规则标的

"""

content += f"""---
**更新时间**：{datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}
**总仓位上限**：{result['emotion']['总仓位上限']}%
"""

# 覆盖写入关注股.md
with open('/Users/yuefengshen/.qclaw/workspace-1gwpiwf3hr163jz5/trading/关注股.md', 'w') as f:
    f.write(content)

print("✅ 关注股.md已更新")
```

---

## 步骤4：发送消息给用户

```python
import json, subprocess

# 读取过滤结果
with open('/tmp/lobster_bid_result.json') as f:
    result = json.load(f)

# 构造消息
msg = f"✅ 龙虾竞价选股 {result['date']}\n"
msg += f"情绪：{result['emotion']['涨跌家数']}（{result['emotion']['主导维度']}）\n\n"

for tier, best in result['results'].items():
    msg += f"【{tier}】\n"
    if best:
        msg += f"最优：{best['name']}({best['code']})\n"
        msg += f"- 竞价：高开{best['change_pct']}%，竞量{best['volume']}手\n"
    else:
        msg += "⚠️ 无符合规则标的\n"

# 发送消息
subprocess.run([
    'message',
    '--action', 'send',
    '--channel', 'yuanbao',
    '--to', 'direct:Y4oPshFZbMiblavrV+kZZdcSD5YFmAiKomnSLvNDINcwVFC1HLHzx5qq7AG0zjPq',
    '--message', msg
])
```

---

## 步骤5：写入临时复盘文件（供午间复盘读取）

```python
import json, datetime

# 读取过滤结果
with open('/tmp/lobster_bid_result.json') as f:
    result = json.load(f)

# 写入临时复盘文件
output = f"""# 龙虾竞价选股 {result['date']}

## 情绪判断
- 涨跌家数：{result['emotion']['涨跌家数']}
- 主导维度：{result['emotion']['主导维度']}
- 总仓位上限：{result['emotion']['总仓位上限']}%

## 选股结果
"""

for tier, best in result['results'].items():
    if best:
        output += f"- {tier}：{best['name']}({best['code']})，高开{best['change_pct']}%，竞量{best['volume']}手\n"
    else:
        output += f"- {tier}：无符合规则标的\n"

with open(f'/tmp/lobster_bid_{result["date"]}.md', 'w') as f:
    f.write(output)

print(f"✅ 复盘文件已写入 /tmp/lobster_bid_{result['date']}.md")
```

---

## 🚨 禁止事项

1. **禁止独立分析候选股**
2. **禁止新增股票**
3. **只从盘前候选池过滤**
4. **必须更新关注股.md**

---

## ✅ 完成标志

- [ ] 已读取盘前候选池JSON
- [ ] 已运行Python过滤脚本
- [ ] **已更新关注股.md（覆盖写入）**
- [ ] 已发送消息给用户
- [ ] 已写入临时复盘文件

---

## 附加：Python过滤脚本内容

如果 `/tmp/lobster_bid_filter_v2.py` 不存在，则创建它：

```python
#!/usr/bin/env python3
import json, re

# 读取输入
with open('/tmp/lobster_bid_input.json') as f:
    data = json.load(f)

# 解析竞价数据
bidding_data = {}
for line in data['bidding_raw'].split(';'):
    line = line.strip()
    if not line:
        continue
    m = re.search(r'v_(\w+)="([^"]*)"', line)
    if m:
        code = m.group(1)
        parts = m.group(2).split('~')
        if len(parts) > 36:
            try:
                bidding_data[code] = {
                    'name': parts[1],
                    'change_pct': float(parts[32]) if parts[32] else 0,
                    'volume': int(parts[36]) if parts[36] else 0
                }
            except:
                pass

# 逐档位过滤
results = {}
for tier_name, candidates in data['candidates'].items():
    qualified = []
    for stock in candidates:
        code_key = ('sh' + stock['代码']) if stock['代码'].startswith('6') else ('sz' + stock['代码'])
        if code_key not in bidding_data:
            continue
        bd = bidding_data[code_key]
        change_pct = bd['change_pct']
        volume = bd['volume']
        
        # 过滤条件
        if tier_name == '1.0一进二' and 6 <= change_pct <= 10 and volume >= 150000:
            qualified.append({'name': bd['name'], 'code': stock['代码'], 'change_pct': change_pct, 'volume': volume})
        elif tier_name == '1.0分歧低吸' and -3 <= change_pct <= 0:
            qualified.append({'name': bd['name'], 'code': stock['代码'], 'change_pct': change_pct, 'volume': volume})
        elif tier_name == '2.0板块卡位' and change_pct > 5 and volume >= 100000:
            qualified.append({'name': bd['name'], 'code': stock['代码'], 'change_pct': change_pct, 'volume': volume})
        elif tier_name == '3.0趋势低吸' and -2 <= change_pct <= 3:
            qualified.append({'name': bd['name'], 'code': stock['代码'], 'change_pct': change_pct, 'volume': volume})
    
    # 选最优1个
    if qualified:
        qualified.sort(key=lambda x: x['volume'], reverse=True)
        results[tier_name] = qualified[0]
    else:
        results[tier_name] = None

# 保存结果
output = {
    'date': data['date'],
    'emotion': data['emotion'],
    'results': results
}
with open('/tmp/lobster_bid_result.json', 'w') as f:
    json.dump(output, f, ensure_ascii=False, indent=2)

print("✅ 过滤完成")
```

---

**任务版本**：v9（加入关注股.md更新步骤）
**最后更新**：2026-05-18 13:15


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
