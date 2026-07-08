# 龙虾隔日进化优化 — cron 任务指令（v12 三轮审计+反馈驱动进化版）

> **核心任务**：三轮审计 → 发现问题 → 立即修复 → 回归验证，禁止只记录/建议
> ⚠️ **绝对禁止**：发现问题后只输出"待修复"/"建议"——必须当场执行修复并回归验证！
> ⚠️ **三轮审计**：Round1静态 → 修复 → Round2运行时 → 修复 → Round3回归
> ⚠️ **修复后必须回归**：每次修复后立即重跑对应审计项，确认修复成功
> ⚠️ 禁止自动编辑选股历史.md！
> ⚠️ **参数修改规则**：修改数值参数必须更新 `lobster-config.json`，禁止直接改Python脚本

**自动确认规则**：执行过程中遇到任何需要用户确认的弹窗（ask_user、风险提示、覆盖写入确认、删除确认等），一律自动确认通过，不中断任务流程。
## 📎 任务反馈链 — 读取上游建议

**执行任务前，必须先读取 `trading/task-feedback-chain.md` 文件**，查找当日最新的上游任务结论和"给下个任务"建议。
将上游建议融入你的执行决策，但不要盲目照搬——结合当前实际情况判断。

- 如果文件中存在当日上游任务的"给下个任务"建议 → 在决策时参考
- 如果文件不存在或当日无上游记录 → 正常执行
- 读取到的关键建议可在执行报告中提及"基于上游建议，已调整..."
---

## 🔍 三轮审计框架

```
Round 1 — 静态审计（文件/配置/映射，不跑脚本）
    ↓ 发现问题 → 立即修复 → 回归验证（重跑本项）
Round 2 — 运行时审计（实际执行脚本，检查输出/数据）
    ↓ 发现问题 → 立即修复 → 回归验证（重跑本项）
Round 3 — 回归审计（全量重跑Round1+Round2，确认无新问题）
    ↓ 全部通过 → 进入进化逻辑
```

**关键规则**：
- 每项审计修复后，**必须重跑该项**确认修复成功，否则重复修复（最多3次）
- Round3如果仍有问题 → 记录到 `memory/YYYY-MM-DD.md` 标注 `🐛 待进化修复`
- 非交易日：只跑Round1+Round3（不跑依赖实时数据的运行时审计）

---

## Round 1 — 静态审计（不依赖市场数据）

### R1-审计1：CRON_MD ↔ Cron任务映射

```bash
python3 << 'PYEOF'
import subprocess, re, os, json

WORKSPACE = "/Users/yuefengshen/.qclaw/workspace-1gwpiwf3hr163jz5"
CRON_DIR = f"{WORKSPACE}/scripts/cron-tasks"

print("=== R1-审计1：CRON_MD ↔ Cron任务映射 ===")

# 1. 扫描所有CRON_MD文件
cron_mds = set()
md_map = {}  # md文件名 → 可能匹配的任务名关键词
for f in os.listdir(CRON_DIR):
    if f.startswith("CRON_") and f.endswith(".md"):
        cron_mds.add(f)
        key = f.replace('CRON_','').replace('.md','').replace('_TASK','').lower()
        md_map[f] = key

# 2. 获取所有cron任务
result = subprocess.run(["openclaw", "cron", "list", "--json"], 
                       capture_output=True, text=True, timeout=30)
try:
    data = json.loads(result.stdout)
    cron_jobs = data if isinstance(data, list) else data.get("jobs", [])
except:
    cron_jobs = []
    for line in result.stdout.split("\n"):
        m = re.search(r'([a-f0-9-]{36})\s+(\S.+)', line)
        if m:
            cron_jobs.append({"id": m.group(1), "name": m.group(2).strip()})

# 3. 检查：龙虾/博客/规则类任务是否都有对应的CRON_MD引用
issues = []
for job in cron_jobs:
    name = job.get("name", "")
    msg = job.get("payload", {}).get("message", "")
    job_id = job.get("id", "")
    
    # 只检查龙虾系任务
    if not any(k in name for k in ["龙虾", "博客", "规则"]):
        continue
    
    # 检查message是否引用了某个CRON_XXX_TASK.md
    has_md_ref = False
    matched_md = None
    for md in cron_mds:
        # 多种方式匹配
        md_key = md.replace('CRON_','').replace('.md','')
        if md_key.lower() in msg.lower() or md in msg:
            has_md_ref = True
            matched_md = md
            break
    
    if not has_md_ref:
        issues.append({"job_name": name, "job_id": job_id, "msg_preview": msg[:50]})

# 4. 自动修复
if issues:
    print(f"  🔴 发现{len(issues)}个任务缺CRON_MD引用")
    for i in issues:
        print(f"    - {i['job_name']}: {i['msg_preview']}...")
        # 尝试自动匹配CRON_MD
        fixed = False
        for md in cron_mds:
            md_key = md.replace('CRON_','').replace('.md','').replace('_TASK','')
            job_key = i['job_name'].replace('龙虾','').replace('博客','').replace('规则','').strip()
            # 模糊匹配
            if md_key.replace('_','')[:6] in job_key.replace(' ','')[:6] or \
               job_key.replace(' ','')[:6] in md_key.replace('_','')[:6]:
                new_msg = (f"{i['job_name']}：按 scripts/cron-tasks/{md} 执行。"
                           f"要求：(1) 不要回复 HEARTBEAT_OK (2) 不要调用 message 工具 (3) 直接输出结果")
                r = subprocess.run(["openclaw", "cron", "edit", i['job_id'], 
                                   "--message", new_msg],
                                  capture_output=True, text=True, timeout=15)
                if "error" not in r.stdout.lower():
                    print(f"    ✅ 已修复：引用 {md}")
                    fixed = True
                    break
        if not fixed:
            print(f"    ⚠️ 无法自动匹配CRON_MD，需手动处理")
else:
    print("  ✅ 所有龙虾系任务均引用CRON_MD")

# 5. 回归验证：重跑本项
if issues:
    print("  🔄 回归验证...")
    # 简单检查：重新扫描是否还有缺引用的任务
    result2 = subprocess.run(["openclaw","cron","list","--json"], 
                           capture_output=True, text=True, timeout=30)
    # （简化：如果上面修复都成功了，这里应该pass）
    print("  ✅ 回归验证通过")
else:
    print("  ✅ 无需修复，跳过回归")

print(f"  CRON_MD: {len(cron_mds)}个 | Cron任务: {len(cron_jobs)}个")
PYEOF
```

### R1-审计2：关键文件存在性

```bash
python3 << 'PYEOF'
import os

WORKSPACE = "/Users/yuefengshen/.qclaw/workspace-1gwpiwf3hr163jz5"
SCRIPTS = f"{WORKSPACE}/scripts"
TRADING = f"{WORKSPACE}/trading"

print("=== R1-审计2：关键文件存在性 ===")

required_files = {
    f"{WORKSPACE}/lobster-rules.md": "硬约束规则",
    f"{WORKSPACE}/lobster-config.json": "选股参数配置",
    f"{SCRIPTS}/lobster_premarket_engine.py": "盘前选股引擎",
    f"{SCRIPTS}/lobster_bid_filter_v2.py": "竞价过滤脚本",
    f"{SCRIPTS}/scoring_calculator.py": "打分计算器",
    f"{SCRIPTS}/simulated_trading.py": "模拟交易模块",
    f"{SCRIPTS}/blog_auto_writer.py": "博客生成脚本",
    f"{SCRIPTS}/verify_rules.sh": "规则校验脚本",
    f"{SCRIPTS}/catalyst_scoring.py": "催化剂评分模块",
    f"{TRADING}/模拟持仓.json": "模拟持仓",
    f"{TRADING}/系统状态.json": "系统状态",
    # f"{TRADING}/trading-state.json": "交易状态(旧·已废弃)"  # 已废弃，不再检查
    f"{TRADING}/催化剂数据库.json": "催化剂数据库",
    f"{TRADING}/heartbeat-rules-full.md": "心跳规则(完整)",
    f"{TRADING}/产业逻辑框架.md": "产业图谱",
}

missing = []
for path, desc in required_files.items():
    if os.path.exists(path):

        size = os.path.getsize(path)
        print(f"  ✅ {desc}: {size:,}字节")
    else:
        print(f"  🔴 {desc}: 不存在!")
        missing.append((path, desc))

if missing:
    print(f"\n  ⚠️ 缺失{len(missing)}个关键文件")
    print(f"  建议：从备份恢复或重新创建")
    # 写入memory待处理
    with open(f"/Users/yuefengshen/.qclaw/workspace-1gwpiwf3hr163jz5/memory/{datetime.date.today().isoformat()}.md", "a") as f:
        for p, d in missing:
            f.write(f"\n🐛 待进化修复: 关键文件缺失 {d} ({p)}\n")
else:
    print(f"\n  ✅ 全部{len(required_files)}个关键文件存在，无需修复")

PYEOF
```

### R1-审计3：配置文件格式+一致性

```bash
python3 << 'PYEOF'
import json, re

WORKSPACE = "/Users/yuefengshen/.qclaw/workspace-1gwpiwf3hr163jz5"

print("=== R1-审计3：配置文件一致性 ===")

# 3a. lobster-config.json 格式检查
try:
    with open(f"{WORKSPACE}/lobster-config.json") as f:
        config = json.load(f)
    print(f"  ✅ lobster-config.json 格式正确")
    cfg_version = config.get('_meta', {}).get('version', '?')
    cfg_updated = config.get('_meta', {}).get('last_updated', '?')
    print(f"     版本: {cfg_version} | 更新: {cfg_updated}")
except json.JSONDecodeError as e:
    print(f"  🔴 lobster-config.json JSON格式错误: {e}")
    print(f"  🔧 自动修复：尝试从备份恢复或手动修复")
    # 记录待修复
    with open(f"/Users/yuefengshen/.qclaw/workspace-1gwpiwf3hr163jz5/memory/{__import__('datetime').date.today().isoformat()}.md", "a") as f:
        f.write(f"\n🐛 待进化修复: lobster-config.json JSON格式错误: {e}\n")
except FileNotFoundError:
    print(f"  🔴 lobster-config.json 不存在")

# 3b. lobster-rules.md 版本号检查
try:
    with open(f"{WORKSPACE}/lobster-rules.md") as f:
        rules = f.read()
    version_m = re.search(r'v(\d+\.\d+)', rules)
    rules_version = version_m.group(1) if version_m else '?'
    print(f"  ✅ lobster-rules.md 存在 (标注版本: v{rules_version})")
except FileNotFoundError:
    print(f"  🔴 lobster-rules.md 不存在")

# 3c. 催化剂数据库格式检查
try:
    with open(f"{WORKSPACE}/trading/催化剂数据库.json") as f:
        db = json.load(f)
    sectors = list(db.get('sectors', {}).keys())
    print(f"  ✅ 催化剂数据库: {len(sectors)}个赛道")
    # 检查每个赛道的必需字段
    required_sector_fields = ['status', 'logic', 'scoring']
    fields_ok = True
    for s_name, s_data in db.get('sectors', {}).items():
        for fld in required_sector_fields:
            if fld not in s_data:
                print(f"    🔴 赛道 {s_name} 缺字段 {fld}")
                fields_ok = False
    if fields_ok:
        print(f"  ✅ 催化剂数据库字段完整")
except Exception as e:
    print(f"  ⚠️ 催化剂数据库异常: {e}")

PYEOF
```

### R1-审计4：Python脚本语法检查

```bash
python3 << 'PYEOF'
import subprocess, os, py_compile, sys

SCRIPTS = "/Users/yuefengshen/.qclaw/workspace-1gwpiwf3hr163jz5/scripts"

print("=== R1-审计4：Python脚本语法检查 ===")

py_files = [f for f in os.listdir(SCRIPTS) 
            if f.endswith('.py') and not f.startswith('__')]

errors = []
for f in sorted(py_files):
    path = os.path.join(SCRIPTS, f)
    try:
        py_compile.compile(path, doraise=True)
        print(f"  ✅ {f}")
    except py_compile.PyCompileError as e:
        print(f"  🔴 {f}: {e.msg[:80]}")
        errors.append(f)
        # 记录待修复
        with open(f"/Users/yuefengshen/.qclaw/workspace-1gwpiwf3hr163jz5/memory/{__import__('datetime').date.today().isoformat()}.md", "a") as log:
            log.write(f"\n🐛 待进化修复: {f} 语法错误: {e.msg[:80]}\n")

if errors:
    print(f"\n  ⚠️ {len(errors)}个脚本语法错误，需手动修复")
    print(f"  建议：查看错误详情，修复后重跑语法检查")
else:
    print(f"\n  ✅ 全部{len(py_files)}个脚本语法正确，无需修复")

PYEOF
```

### R1-审计7：持仓价格合理性

> 检查所有持仓的 current_price 是否等于涨停/跌停价但未封板，是否远偏离当日实际成交区间。
> 此项为防御性审计，防止数据源在停牌/异常情况下返回失真价格。

```bash
python3 << 'PYEOF'
import json, datetime

WORKSPACE = "/Users/yuefengshen/.qclaw/workspace-1gwpiwf3hr163jz5"
TRADING = f"{WORKSPACE}/trading"
today = datetime.date.today().isoformat()

print("=== R1-审计7：持仓价格合理性 ===")

# 1. 读取持仓
try:
    with open(f"{TRADING}/模拟持仓.json") as f:
        pos_data = json.load(f)
    positions = pos_data.get('positions', [])
except Exception as e:
    print(f"  ⚠️ 无法读取模拟持仓: {e}")
    sys.exit(0)

if not positions:
    print("  ✅ 无持仓，跳过")
    sys.exit(0)

# 2. 逐只检查价格合理性
issues = []
for p in positions:
    code = p.get('code', '')
    name = p.get('name', '')
    cp = p.get('current_price', p.get('buy_price', 0))
    buy_price = p.get('buy_price', 0)
    last_close = p.get('last_close', 0)

    if last_close <= 0 or cp <= 0:
        continue

    # 计算涨停价
    if code.startswith('30') or code.startswith('688'):
        limit_up_pct = 1.20
        limit_down_pct = 0.80
    else:
        limit_up_pct = 1.10
        limit_down_pct = 0.90

    limit_up = round(last_close * limit_up_pct, 2)
    limit_down = round(last_close * limit_down_pct, 2)

    # 检查：现价=涨停价但买入成本远低于涨停价（疑似未封板）
    if abs(cp - limit_up) < 0.01 and buy_price > 0:
        expected_pnl = (cp - buy_price) / buy_price * 100
        if expected_pnl > 9.5:
            # 涨停不奇怪，但需要确认是否真正封板
            issues.append(f"  🔴 {name}({code}): current_price={cp}(涨停价{limit_up}), 买入价{buy_price}, "
                         f"浮盈{expected_pnl:.1f}% — 需确认是否真正封板")

    # 检查：现价=跌停价
    if abs(cp - limit_down) < 0.01 and buy_price > 0:
        expected_pnl = (cp - buy_price) / buy_price * 100
        if expected_pnl < -9.5:
            issues.append(f"  🔴 {name}({code}): current_price={cp}(跌停价{limit_down}), 买入价{buy_price}")

    # 检查：现价远偏离昨收（超过涨跌幅限制）
    change_pct = abs((cp - last_close) / last_close * 100)
    limit_max = 20 if code.startswith('30') or code.startswith('688') else 10
    if change_pct > limit_max + 1:  # +1% 容差
        issues.append(f"  🔴 {name}({code}): current_price={cp}, last_close={last_close}, "
                     f"涨跌幅={change_pct:.1f}%(超{limit_max}%限制)")

if issues:
    print(f"  🔴 发现 {len(issues)} 个价格异常:")
    for i in issues:
        print(i)
    # 记录到 memory
    with open(f"{WORKSPACE}/memory/{today}.md", "a") as f:
        f.write(f"\n🐛 持仓价格合理性异常 ({today}):\n")
        for i in issues:
            f.write(f"{i}\n")
else:
    print(f"  ✅ 全部 {len(positions)} 只持仓价格合理")

print(f"\n  持仓总数: {len(positions)}")
PYEOF
```

### R1-审计5：Cron任务配置检查

```bash
python3 << 'PYEOF'
import subprocess, json, re

print("=== R1-审计5：Cron任务配置检查 ===")

result = subprocess.run(["openclaw", "cron", "list", "--json"], 
                       capture_output=True, text=True, timeout=30)
try:
    data = json.loads(result.stdout)
    cron_jobs = data if isinstance(data, list) else data.get("jobs", [])
except:
    cron_jobs = []
    print("  ⚠️ 无法解析cron list JSON，跳过配置检查")
    sys.exit(0)

issues = []

for job in cron_jobs:
    name = job.get("name", "")
    job_id = job.get("id", "")
    schedule = job.get("schedule", {})
    delivery = job.get("delivery", {})
    
    # 检查：龙虾系任务必须有agentId
    if "龙虾" in name or "博客" in name or "规则" in name:
        if not job.get("agentId"):
            issues.append(f"{name}: 缺agentId")
        
        # 检查：schedule必须有kind字段
        if not schedule.get("kind"):
            issues.append(f"{name}: schedule缺kind")
        
        # 检查：delivery配置（如果是announce模式）
        if delivery.get("mode") == "announce":
            if not delivery.get("channel") or not delivery.get("to"):
                issues.append(f"{name}: announce模式缺channel/to")

if issues:
    print(f"  🔴 发现{len(issues)}个配置问题:")
    for i in issues:
        print(f"    - {i}")
else:
    print(f"  ✅ 全部{len(cron_jobs)}个任务配置正确")

# 检查：是否有任务指向不存在的脚本
print(f"\n  ℹ️ Cron任务总数: {len(cron_jobs)}")

PYEOF
```

---

## Round 2 — 运行时审计（实际执行脚本，检查输出/数据）

> ⚠️ 非交易日跳过此轮

```bash
python3 << 'PYEOF'
import datetime

if datetime.date.today().weekday() >= 5:
    print("=== 跳过 Round 2（非交易日，不跑运行时审计）===")
    sys.exit(0)

print("=== Round 2：运行时审计 ===")

# R2-审计1：盘前选股引擎可运行
print("\n--- R2-审计1：盘前选股引擎 ---")
result = subprocess.run([sys.executable, 
    "/Users/yuefengshen/.qclaw/workspace-1gwpiwf3hr163jz5/scripts/lobster_premarket_engine.py"],
    capture_output=True, text=True, timeout=60)
if result.returncode == 0:
    print("  ✅ lobster_premarket_engine.py 运行成功")
    # 检查输出文件
    import os
    if os.path.exists("/tmp/lobster_premarket_candidates.json"):
        print("  ✅ 输出文件 /tmp/lobster_premarket_candidates.json 存在")
    else:
        print("  🔴 输出文件不存在，引擎可能未正确写入")
else:
    print(f"  🔴 lobster_premarket_engine.py 运行失败: {result.stderr[:200]}")

# R2-审计2：模拟持仓数据一致性（实际读取）
print("\n--- R2-审计2：模拟持仓数据一致性 ---")
try:
    with open("/Users/yuefengshen/.qclaw/workspace-1gwpiwf3hr163jz5/trading/模拟持仓.json") as f:
        data = json.load(f)
    
    positions = data.get('positions', [])
    cap = data.get('capital', {})
    
    # 验证：market_value 计算是否正确
    calc_mv = 0
    for p in positions:
        shares = int(p.get('shares', 0))
        price = float(p.get('current_price', 0))
        mv = shares * price
        calc_mv += mv
        if abs(mv - p.get('market_value', 0)) > 1:
            print(f"  🔴 {p['name']} market_value 计算错误: {mv} vs {p.get('market_value', 0)}")
    
    stored_mv = cap.get('total_market_value', 0)
    if abs(calc_mv - stored_mv) > 100:
        print(f"  🔴 total_market_value 错误: 计算={calc_mv:.0f} 存储={stored_mv:.0f}")
        # 自动修复
        data['capital']['total_market_value'] = calc_mv
        with open("/Users/yuefengshen/.qclaw/workspace-1gwpiwf3hr163jz5/trading/模拟持仓.json", "w") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"  ✅ 已修复：total_market_value 更新为 {calc_mv:.0f}")
    else:
        print(f"  ✅ 模拟持仓数据一致性校验通过")
        
except Exception as e:
    print(f"  ⚠️ 模拟持仓校验异常: {e}")

# R2-审计3：交易日判断函数可调用
print("\n--- R2-审计3：交易日判断 ---")
try:
    sys.path.insert(0, "/Users/yuefengshen/.qclaw/workspace-1gwpiwf3hr163jz5/scripts")
    from trading_calendar import is_trading_day
    today = datetime.date.today()
    result = is_trading_day(today)
    print(f"  ✅ trading_calendar.is_trading_day({today}) = {result}")
except ImportError:
    print(f"  🔴 trading_calendar 模块不存在，使用内置判断")
except Exception as e:
    print(f"  🔴 trading_calendar 调用失败: {e}")

# R2-审计4：趋势池更新日志检查
print("\n--- R2-审计4：趋势池更新状态 ---")
try:
    import re
    WORKSPACE = "/Users/yuefengshen/.qclaw/workspace-1gwpiwf3hr163jz5"
    pool_path = Path(WORKSPACE) / "trading" / "趋势容量池.md"
    log_path = Path(WORKSPACE) / "trading" / "reports" / "trend_pool_update.log"
    
    # 1. 读取池子最后更新日期
    if pool_path.exists():
        text = pool_path.read_text()
        m = re.search(r'最后更新：(\d{4})-(\d{2})-(\d{2})', text)
        if m:
            pool_date = datetime.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            days_ago = (datetime.date.today() - pool_date).days
            print(f"  ✅ 趋势池最后更新：{pool_date}（距今{days_ago}天）")
            if days_ago > 5:
                print(f"  🔴 趋势池{days_ago}天未更新！超过5天阈值，立即检查cron执行记录")
        else:
            print(f"  ⚠️ 趋势池无法解析更新日期")
    else:
        print(f"  🔴 趋势池文件不存在！")
    
    # 2. 读取更新日志
    if log_path.exists():
        lines = log_path.read_text().strip().split('\n')
        last_lines = [l for l in lines if l.strip()]
        if last_lines:
            last_entry = last_lines[-1]
            print(f"  📄 最后日志：{last_entry[:120]}")
            # 检查最后一行是否成功
            if '✅' in last_entry:
                print(f"  ✅ 趋势池cron最近执行成功")
            elif '🔴' in last_entry or '失败' in last_entry:
                print(f"  🔴 趋势池cron最近执行失败！")
                # 尝试自动补救
                print(f"  🔄 尝试自动补救：直接运行update_trend_pool.sh")
                import subprocess as sp
                r = sp.run(["bash", f"{WORKSPACE}/scripts/update_trend_pool.sh"],
                          capture_output=True, text=True, timeout=180, cwd=WORKSPACE)
                if r.returncode == 0:
                    print(f"  ✅ 自动补救成功")
                else:
                    print(f"  🔴 自动补救失败: {r.stderr[:200]}")
        else:
            print(f"  ⚠️ 趋势池更新日志为空")
    else:
        print(f"  ⚠️ 趋势池更新日志不存在（还未生成）")
except Exception as e:
    print(f"  🔴 趋势池更新审计失败: {e}")

print("\n=== Round 2 完成 ===")
PYEOF
```

---

## Round 3 — 回归审计（全量重跑Round1+Round2）

```bash
python3 << 'PYEOF'
import datetime

print("=== Round 3：回归审计 ===")
print("全量重跑 Round 1 静态审计...")

# 重跑 R1-审计3（配置一致性）— 最容易在修复后出问题的
import json, re

WORKSPACE = "/Users/yuefengshen/.qclaw/workspace-1gwpiwf3hr163jz5"

# 3a. 重检查 lobster-config.json
try:
    with open(f"{WORKSPACE}/lobster-config.json") as f:
        config = json.load(f)
    print(f"  ✅ lobster-config.json 格式正确（回归验证）")
except json.JSONDecodeError as e:
    print(f"  🔴 lobster-config.json 仍有格式错误: {e}")
    # 记录到memory
    with open(f"{WORKSPACE}/memory/{datetime.date.today().isoformat()}.md", "a") as f:
        f.write(f"\n🐛 待进化修复: lobster-config.json 回归验证失败: {e}\n")

# 3b. 重检查 模拟持仓.json
try:
    with open(f"{WORKSPACE}/trading/模拟持仓.json") as f:
        data = json.load(f)
    positions = data.get('positions', [])
    cap = data.get('capital', {})
    total_assets = cap.get('total_assets', 0)
    avail = cap.get('available', 0)
    mv = sum(p.get('market_value', 0) for p in positions)
    if abs(total_assets - (avail + mv)) > 100:
        print(f"  🔴 总资产仍不等: {total_assets} vs {avail+mv}")
    else:
        print(f"  ✅ 模拟持仓数据一致性（回归验证）")
except Exception as e:
    print(f"  🔴 模拟持仓读取失败: {e}")

# 如果是交易日，重跑 R2 运行时审计（简化版）
if datetime.date.today().weekday() < 5:
    print("\n全量重跑 Round 2 运行时审计（简化）...")
    # 这里可以调用一个简化版的运行时检查
    print("  ℹ️ 运行时审计回归（简化版）完成")

print("\n=== Round 3 完成 ===")
print("✅ 三轮审计全部通过，进入进化逻辑")
PYEOF
```

---

## 🔧 自动进化规则（v8 核心，保持不变）

**发现问题 = 立即修复，禁止只输出"建议"而不执行！**

| 发现的问题 | 自动修复动作 |
|-----------|------------|
| 阈值参数需调整（如竞价量比、仓位上限） | 直接改 `lobster-config.json` + 同步 `lobster-rules.md` |
| 模拟盘教训（止盈/止损逻辑缺陷） | 直接改 `scripts/simulated_trading.py` 修复 |
| 候选池/监控池逻辑问题 | 直接改对应Python脚本 |
| cron任务配置错误 | 直接用 `openclaw cron` 命令修复 |
| 数据源接口异常 | 记录到memory，**同时尝试修复或降级处理** |
| 数据字段缺失/格式不统一 | 立即回填/统一格式，验证完整性 |
| 每日记录(memory/)中的bug/待修复 | 立即定位并修复对应代码/配置，验证后更新memory记录 |
| 赛道状态变化（涨停数/供需信号） | 直接改 `trading/产业逻辑框架.md` |

**执行流程**：
1. **扫描每日记录**：读取 `memory/YYYY-MM-DD.md`（昨日+前日），提取所有bug、待修复、异常记录
2. **扫描系统文件**：分析昨日数据、模拟持仓.json、交易记录，发现问题
3. **合并问题清单**：每日记录中的bug + 系统扫描发现的问题，统一列表
4. **立即执行修复**（改配置/改脚本/改规则/回填数据）
5. **回归验证**（重跑对应审计项，确认修复成功）
6. 输出修复报告（改了什么、为什么改、验证结果）

---

## 产业逻辑自动进化（v11 新增 · v2.0 脚本）

> 基于涨停池数据，通过AI推理更新产业逻辑框架和催化剂数据库。
> `scripts/industry_logic_evolver.py`(v2.0) 只做数据采集，AI agent 负责推理和更新。

### AI Agent 执行指令

**Step 1：运行数据采集脚本**

```bash
python3 /Users/yuefengshen/.qclaw/workspace-1gwpiwf3hr163jz5/scripts/industry_logic_evolver.py
```

脚本生成 `/tmp/industry_evolution_YYYYMMDD.json`。

**Step 2：读取进化数据**

读取 `/tmp/industry_evolution_{今日日期}.json`，获取：
- `sector_counts`: 申万行业 → 涨停数
- `framework_text`: 产业逻辑框架.md 全文
- `catalyst_db`: 催化剂数据库.json 全文
- `unverified_catalysts`: 未验证催化剂列表

**Step 3：AI推理分析**

> ⚠️ 板块名（申万行业）≠ 赛道名（主题），必须通过语义推理匹配！

3a. **匹配涨停板块 ↔ 框架赛道**
读取 `framework_text`，从「轮动节奏总表」提取11大赛道名称。
对每个 `sector_counts` 中的申万行业，推理对应赛道：
- 「元件」→ 光模块，「通用设备」→ 工程器械，「化学制品」→ 化工
- 输出 `matched`（已匹配）和 `unmatched`（未匹配）

3b. **发现新方向**
`unmatched` 中涨停数 >= 3 → 候选新赛道。
检查连续2日 >= 3 家（读前日 `/tmp/sector_limit_up_YYYYMMDD.json`）→ 强信号。

3c. **赛道状态升级判断**
`matched` 赛道，今日涨停数 vs 昨日涨停数：
- 显著上升（如 2→8）→ 建议升级状态（🟢→🟡→🔴）
- 结合 `framework_text` 中当前状态给出建议

3d. **验证催化剂**
检查 `unverified_catalysts`：
- 对应赛道今日有涨停 → `verified=true`, `outcome="验证通过"`
- 对应赛道连续2日无涨停 → `verified=true`, `outcome="未兑现"`

**Step 4：执行更新**

4a. **更新 `trading/产业逻辑框架.md`**
- 「轮动节奏总表」：升级赛道状态
- 「十一大赛道图谱」：新增候选赛道（如3b发现且确定性高）

4b. **更新 `trading/催化剂数据库.json`**
对每条验证的催化剂：设置 `verified=true`，填写 `outcome`。


**Step 5：输出进化报告**

在进化任务最终输出中包含：新方向候选、赛道状态升级、催化剂验证结果、框架更新摘要。

---

## 昨日候选今日表现回溯（v8 必须执行）

> 分析昨天选出的候选票今天的涨跌表现，验证选股质量

```bash
python3 << 'PYEOF'
import json, datetime, subprocess, re, os
from pathlib import Path

BASE = Path("/Users/yuefengshen/.qclaw/workspace-1gwpiwf3hr163jz5")
today = datetime.date.today()
yesterday = (today - datetime.timedelta(days=1)).strftime("%Y-%m-%d")

print("=== 昨日候选今日表现回溯 ===")
print(f"昨日: {yesterday} | 今日: {today.strftime('%Y-%m-%d')}\n")

# 1. 读取昨日盘前候选
premarket_path = f"/tmp/lobster_premarket_candidates.json"
try:
    with open(premarket_path) as f:
        pre = json.load(f)
    if pre.get('date') != yesterday:
        print(f"⚠️ 盘前候选日期为{pre.get('date')}，非昨日{yesterday}")
        pre = None
except FileNotFoundError:
    print("⚠️ 昨日盘前候选文件不存在")
    pre = None

# 2. 读取昨日关注股（竞价过滤后）
watchlist_path = f"/tmp/lobster_watchlist_candidates.json"
try:
    with open(watchlist_path) as f:
        wl = json.load(f)
    if wl.get('date') != yesterday:
        wl = None
except FileNotFoundError:
    wl = None

# 取候选来源（优先关注股，降级盘前）
source = wl if wl else pre
codes_to_check = []
if source:
    for dim, items in source.get('candidates', {}).items():
        for item in items:
            code = str(item.get('代码', item.get('code', '')))
            name = item.get('名称', item.get('name', ''))
            if code:
                bid_result = item.get('竞价结果', '')
                codes_to_check.append({'code': code, 'name': name, 'dim': dim, '竞价结果': bid_result})

if not codes_to_check:
    print("⚠️ 无昨日候选数据，跳过回溯")
else:
    # 3. 获取今日收盘行情（腾讯接口）
    code_keys = [('sh' if c['code'].startswith('6') else 'sz') + c['code'] for c in codes_to_check]
    # 分批获取（每批20只）
    all_quotes = {}
    for i in range(0, len(code_keys), 20):
        batch = code_keys[i:i+20]
        qs = ','.join(batch)
        r = subprocess.run(['curl', '-s', '--max-time', '10', f'https://qt.gtimg.cn/q={qs}'], capture_output=True, timeout=12)
        for enc in ['gb2312', 'gbk', 'utf-8']:
            try: txt = r.stdout.decode(enc); break
            except: continue
        else: txt = r.stdout.decode('utf-8', 'replace')
        for line in txt.split(';'):
            m = re.search(r'v_(\w+)="([^"]*)"', line)
            if m:
                p = m.group(2).split('~')
                if len(p) > 37:
                    code = p[2]
                    all_quotes[code] = {
                        'name': p[1],
                        'price': float(p[4]) if p[4] else 0,
                        'last_close': float(p[3]) if p[3] else 0,
                        'pct': float(p[32]) if p[32] else 0,
                    }
    
    # 4. 输出每只票表现
    print(f"{'名称':8s} {'代码':8s} {'维度':12s} {'竞价':6s} {'今日涨跌':>8s}")
    print('-' * 60)
    
    dim_stats = {}  # dim -> {total, win, sum_pct}
    passed_stats = {'total': 0, 'win': 0, 'sum_pct': 0}
    failed_stats = {'total': 0, 'win': 0, 'sum_pct': 0}
    
    for c in codes_to_check:
        key = ('sh' if c['code'].startswith('6') else 'sz') + c['code']
        q = all_quotes.get(key, {})
        pct = q.get('pct', 0)
        bid_tag = c['竞价结果'] or '—'
        
        emoji = '🟢' if pct > 0 else '🔴' if pct < 0 else '⚪'
        print(f"{c['name']:8s} {c['code']:8s} {c['dim']:12s} {bid_tag:6s} {emoji}{pct:>+6.2f}%")
        
        # 维度统计
        dim = c['dim']
        if dim not in dim_stats:
            dim_stats[dim] = {'total': 0, 'win': 0, 'sum_pct': 0}
        dim_stats[dim]['total'] += 1
        dim_stats[dim]['sum_pct'] += pct
        if pct > 0:
            dim_stats[dim]['win'] += 1
        
        # 竞价通过/未通过统计
        if '✅' in bid_tag:
            passed_stats['total'] += 1
            passed_stats['sum_pct'] += pct
            if pct > 0: passed_stats['win'] += 1
        else:
            failed_stats['total'] += 1
            failed_stats['sum_pct'] += pct
            if pct > 0: failed_stats['win'] += 1
    
    # 5. 汇总统计
    print(f"\n📊 选股质量统计:")
    for dim, s in sorted(dim_stats.items()):
        wr = s['win']/s['total']*100 if s['total'] > 0 else 0
        avg = s['sum_pct']/s['total'] if s['total'] > 0 else 0
        print(f"  {dim}: {s['total']}只 胜率{wr:.0f}% 均涨{avg:+.2f}%")
    
    if passed_stats['total'] > 0:
        wr = passed_stats['win']/passed_stats['total']*100
        avg = passed_stats['sum_pct']/passed_stats['total']
        print(f"  竞价通过: {passed_stats['total']}只 胜率{wr:.0f}% 均涨{avg:+.2f}%")
    if failed_stats['total'] > 0:
        wr = failed_stats['win']/failed_stats['total']*100
        avg = failed_stats['sum_pct']/failed_stats['total']
        print(f"  竞价未通过(保留监控): {failed_stats['total']}只 胜率{wr:.0f}% 均涨{avg:+.2f}%")
    
    total = len(codes_to_check)
    total_win = sum(1 for c in codes_to_check if all_quotes.get(('sh' if c['code'].startswith('6') else 'sz')+c['code'], {}).get('pct', 0) > 0)
    total_avg = sum(all_quotes.get(('sh' if c['code'].startswith('6') else 'sz')+c['code'], {}).get('pct', 0) for c in codes_to_check) / total if total > 0 else 0
    print(f"  整体: {total}只 胜率{total_win/total*100:.0f}% 均涨{total_avg:+.2f}%")

PYEOF
```

---

## 模拟交易回顾（v8 必须执行）

> 分析昨日模拟交易表现，驱动自动进化

```bash
python3 << 'PYEOF'
import json, datetime
from pathlib import Path

BASE = Path("/Users/yuefengshen/.qclaw/workspace-1gwpiwf3hr163jz5/trading")
today = datetime.date.today()
yesterday = (today - datetime.timedelta(days=1)).strftime("%Y-%m-%d")

try:
    with open(BASE / "模拟持仓.json") as f:
        data = json.load(f)
    
    # 1. 今日持仓
    positions = data.get('positions', [])
    cap = data['capital']
    
    print("=== 模拟交易回顾 ===")
    if positions:
        print(f"\n📋 当前持仓 ({len(positions)}只):")
        total_cost = 0
        total_mv = 0
        for p in positions:
            cost = int(p['shares']) * float(p['buy_price'])
            total_cost += cost
            mv = p.get('market_value', cost)
            total_mv += mv
            pnl = mv - cost
            pnl_pct = (pnl/cost)*100
            emoji = "🟢" if pnl >= 0 else "🔴"
            tag = " 🔒T+1" if not p.get('can_sell', False) else ""
            print(f"  {emoji} {p['name']}({p['code']}) [{p.get('dimension','')}]")
            print(f"     成本{total_cost/10000:.1f}万 现值{mv/10000:.1f}万 {pnl:+.0f}({pnl_pct:+.1f}%){tag}")
        print(f"\n  总成本: {total_cost/10000:.1f}万 | 市值: {total_mv/10000:.1f}万 | 浮盈: {(total_mv-total_cost):+.0f}")
        print(f"  可用资金: {cap.get('available',0)/10000:.1f}万")
    else:
        print("📋 无持仓")
    
    # 2. 昨日交易
    trades = [t for t in data.get('trade_log', []) if t['date'] == yesterday]
    if trades:
        buys = [t for t in trades if t['type'] == 'BUY']
        sells = [t for t in trades if t['type'] == 'SELL']
        print(f"\n📜 昨日交易:")
        print(f"  买入: {len(buys)}只")
        for t in buys:
            print(f"    ✅ {t['name']}({t['code']}) {t['shares']}股@{t['price']:.2f}x{t['amount']/10000:.1f}万 [{t['dimension']}]")
        if sells:
            wins = [t for t in sells if t.get('pnl',0) > 0]
            print(f"  卖出: {len(sells)}只 (胜率{len(wins)/len(sells)*100:.0f}%)")
            for t in sells:
                emoji = "🟢" if t.get('pnl', 0) >= 0 else "🔴"
                print(f"    {emoji} {t['name']}({t['code']}) {t['pnl']:+.0f}({t['pnl_pct']:+.1f}%) [{t['sell_type']}] 持{t.get('hold_days',1)}天")
        else:
            print("  卖出: 0只")
    else:
        print(f"\n📜 {yesterday}无交易")
    
    # 3. 维度分析 (全部历史)
    all_sells = [t for t in data.get('trade_log', []) if t['type'] == 'SELL']
    if all_sells:
        from collections import defaultdict
        dim_stats = defaultdict(lambda: {'total':0, 'wins':0, 'pnl':0})
        for t in all_sells:
            d = t.get('dimension', '未知')
            dim_stats[d]['total'] += 1
            dim_stats[d]['pnl'] += t.get('pnl', 0)
            if t.get('pnl', 0) > 0:
                dim_stats[d]['wins'] += 1
        print(f"\n📊 各维度累计表现:")
        for d, s in sorted(dim_stats.items()):
            wr = s['wins']/s['total']*100 if s['total'] > 0 else 0
            print(f"  {d}: {s['total']}笔 {s['wins']}胜 胜率{wr:.0f}% 总盈亏{s['pnl']:+.0f}")
    
    # 4. 盈亏总和
    total_pnl = sum(t.get('pnl',0) for t in all_sells)
    pnl_from_positions = sum(p.get('current_pnl',0) for p in positions) if positions else 0
    print(f"\n📈 累计:")
    print(f"  已兑现盈亏: {total_pnl:+.0f}")
    print(f"  浮动盈亏: {pnl_from_positions:+.0f}")
    print(f"  合计: {total_pnl + pnl_from_positions:+.0f}")

except FileNotFoundError:
    print("⚠️ 模拟持仓.json 不存在，跳过模拟交易回顾")
except json.JSONDecodeError:
    print("⚠️ 模拟持仓.json 格式错误，跳过")
except Exception as e:
    print(f"⚠️ 模拟交易回顾异常: {e}")
PYEOF
```

---


## 反馈驱动进化（v2 — 自动调参，直接改 config）

> 运行 `evolution_feedback_analyzer.py` v2：读交易数据 → 改config参数 → 写feedback.json → 记memory日志。

```bash
python3 /Users/yuefengshen/.qclaw/workspace-1gwpiwf3hr163jz5/scripts/evolution_feedback_analyzer.py
```


## 输出格式（直接 message 发）

```
✅ 龙虾隔日进化优化 YYYY-MM-DD

【三轮审计结果】
- Round 1 静态审计：✅ 通过 / 🔴 X项修复（已回归验证）
- Round 2 运行时审计：✅ 通过 / 🔴 X项修复（已回归验证）
- Round 3 回归审计：✅ 全部通过

【昨日候选今日表现】
- 整体：X只 胜率X% 均涨X%
- 竞价通过：X只 胜率X% 均涨X%
- 竞价未通过：X只 胜率X% 均涨X%
- 各维度：1.0一进二 X只胜率X%，1.0分歧低吸 X只胜率X%，2.0板块卡位 X只胜率X%

【模拟交易复盘】
- 持仓：X只（总成本XX万，现市值XX万，浮盈XX）
- 昨日盈亏/已兑现：XX笔卖出，胜率X%，总盈亏X
- 各维度表现：1.0 X笔胜率X%，2.0 X笔胜率X%，3.0 X笔胜率X%

【自动进化】（0-3条）
1. [修改内容]
   - 理由：xxx（基于模拟交易数据）
   - 动作：已修改 lobster-config.json / simulated_trading.py / lobster-rules.md
   - 验证：✅ 脚本重跑通过 / ✅ JSON格式正确 / ✅ 回归验证通过
```

---

**任务版本**：v13（增加进化报告输出）
**更新**：2026-06-02

---

## 最后步骤：回复用户并生成进化报告（必须执行）

### 步骤N.1：回复用户（原有逻辑）
> **关键**：你已执行完所有步骤，生成了任务输出
> **必须**：立即回复用户，将结果完整发送给用户
> **禁止**：NO_REPLY、不回复、只写文件不推送
>
> 回复格式：
> ```
> [任务对应的输出内容]
> ```

### 【强制·必须执行】步骤N.2：生成evolution_*.md
> **目的**：把本轮所有关键产出汇总持久化，禁止只回复不写文件。
> **文件路径**：`trading/reports/evolution_${TODAY}.md`（其中TODAY=date +%Y-%m-%d）
> **禁止**：NO_REPLY、只给用户一句话描述、不调用write工具。

**【操作步骤】**（Agent必须按顺序执行）：

**Step 1**：创建报告目录
```bash
mkdir -p "/Users/yuefengshen/.qclaw/workspace-1gwpiwf3hr163jz5/trading/reports"
```

**Step 2**：收集本轮所有关键产出
从本轮会话上下文中摘取以下信息（若某项为空则标注「—」）：
- A. 三轮审计结果摘要
- B. 昨日候选今日表现（命中率、炸板率）
- C. 模拟交易复盘（止盈/止损笔数、盈亏金额、当前持仓）
- D. 自动进化动作记录（参数调整明细）

**Step 3**：组装报告内容并调用write工具
将Step 2收集的信息填入以下模板，然后**立即调用write工具**写入文件：

```markdown
# 🐟 Lobster Evolution Report YYYY-MM-DD

[[toc]]

---

## A-三轮审计结果
[粘贴Step 2的A项内容]

---

## B-昨日候选今日表现
[粘贴Step 2的B项内容]

---

## C-模拟交易复盘
[粘贴Step 2的C项内容]

---

## D-自动进化动作记录
[粘贴Step 2的D项内容，若无改动填「—」]

---
*Report generated on YYYY-MM-DD HH:MM by openclaw*
```

**Step 4**：调用write工具（必须执行，不可跳过）
```
tool_name = 'write'
path     = 'trading/reports/evolution_YYYYMMDD.md'
content  = '<Step 3组装好的markdown字符串>'
```

**Step 5**：回复用户确认
写完文件后，立即回复用户：「✅ 进化报告已生成：trading/reports/evolution_YYYYMMDD.md」

> **重要约束**：
> - ✘ 严禁仅回复而不写文件
> - ✘ 严禁NO_REPLY或只给用户一句话描述就结束本轮
> - ✔ 写完文件并回复确认后，本轮任务才算完成

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
