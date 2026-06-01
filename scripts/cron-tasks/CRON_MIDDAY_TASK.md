# 龙虾午间复盘 — cron 任务指令（v6）

> **执行时间**：交易日 11:30
> **前置任务**：读取今日盘前选股+竞价选股结果
> **核心任务**：分析上午表现 + 调整下午策略

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
        errors.append(f"盘前候选池JSON日期={data.get('date')}，非今天{today}，可能是昨天的数据")
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
    print(f"\n⚠️ 午间复盘将在不完整数据下执行，结论可能不准确！")
else:
    print("\n✅ 所有前置校验通过")
PYEOF
```

## 步骤0.5：读取最新规则（必做）

```bash
# 读取硬约束规则
cat ~/.qclaw/workspace-1gwpiwf3hr163jz5/lobster-rules.md | head -80

# 读取心跳规则（精简版）
cat ~/.qclaw/workspace-1gwpiwf3hr163jz5/HEARTBEAT.md
```

---

## 步骤1：获取上午市场数据 + 情绪面板构建（实时）

```bash
python3 << 'PYEOF'
import subprocess, re, datetime, json, os

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
            price = parts[4]  # parts[4]=当前价
            pct = parts[32]
            pre_close = parts[3]  # parts[3]=昨收
            high = parts[33] if len(parts) > 33 else "?"
            low = parts[34] if len(parts) > 34 else "?"
            indices[name] = {"price": price, "pct": pct, "pre_close": pre_close, "high": high, "low": low}
            print(f"{name}: {price} ({pct}%) Hi{high} Lo{low}")

# 涨跌家数（legulegu，实时）
r2 = subprocess.run(["curl","-s","-L","--max-time","15","-A","Mozilla/5.0","https://legulegu.com/stockdata/market-activity"], capture_output=True, text=True, timeout=20)
m2 = re.search(r'content="(2026-[^"]+)"', r2.stdout)
emotion_text = m2.group(1) if m2 else "获取失败"
print(f"\n涨跌家数: {emotion_text}")

# 解析数字
m_up = re.search(r'(\d+)家上涨', emotion_text)
m_down = re.search(r'(\d+)家下跌', emotion_text)
m_zt = re.search(r'(\d+)家涨停', emotion_text)
m_dt = re.search(r'(\d+)家跌停', emotion_text)

up_count = int(m_up.group(1)) if m_up else 0
down_count = int(m_down.group(1)) if m_down else 0
zt_count = int(m_zt.group(1)) if m_zt else 0
dt_count = int(m_dt.group(1)) if m_dt else 0

# ===== 情绪增强：读取盘前情绪数据做对比 =====
pre_up = None
pre_emotion = None
emotion_change = ""
try:
    with open('/tmp/lobster_premarket_candidates.json') as f:
        pre_data = json.load(f)
    pre_up = pre_data.get('emotion', {}).get('涨跌家数', None)
    pre_emotion = pre_data.get('emotion', {}).get('情绪', None)
    if pre_up:
        delta = up_count - pre_up
        if delta > 300:
            emotion_change = f"📈 较盘前+{delta}（修复中）"
        elif delta < -300:
            emotion_change = f"📉 较盘前{delta}（恶化中）"
        else:
            emotion_change = f"➡️ 较盘前{delta:+d}（稳定）"
except:
    pass

# 情绪判定
if up_count < 1000:
    emotion = "🚨 冰点"
elif up_count < 1500:
    emotion = "⚠️ 偏弱"
elif up_count < 2500:
    emotion = "✅ 正常"
elif up_count < 3500:
    emotion = "🔥 高潮"
else:
    emotion = "🔴 极度高潮"

# 维度判定
if up_count < 1500:
    dimension = "1.0"
    pos_limit = 3
    strategy = "打板+分歧低吸"
elif up_count < 2500:
    dimension = "1.0+3.0"
    pos_limit = 5
    strategy = "打板+趋势低吸"
elif up_count < 3500:
    dimension = "2.0+1.0"
    pos_limit = 7
    strategy = "板块卡位+高低切"
else:
    dimension = "辅助"
    pos_limit = 2
    strategy = "只卖不买"

print(f"\n{'='*50}")
print(f"📊 情绪面板（11:30）")
print(f"{'='*50}")
print(f"涨跌家数：{up_count}涨 {down_count}跌")
print(f"涨停跌停：{zt_count}涨停 {dt_count}跌停")
print(f"情绪判定：{emotion}")
if emotion_change:
    print(f"情绪变化：{emotion_change}")
print(f"主导维度：{dimension}")
print(f"仓位上限：{pos_limit}成")
print(f"适用策略：{strategy}")
print(f"{'='*50}")

# 保存到文件
result = {
    "time": "11:30",
    "indices": indices,
    "up_count": up_count,
    "down_count": down_count,
    "zt_count": zt_count,
    "dt_count": dt_count,
    "emotion": emotion,
    "emotion_change": emotion_change,
    "dimension": dimension,
    "pos_limit": pos_limit,
    "strategy": strategy,
    "emotion_text": emotion_text,
    "pre_up": pre_up,
    "pre_emotion": pre_emotion
}
with open("/tmp/lobster_midday_data.json", "w") as f:
    json.dump(result, f, ensure_ascii=False, indent=2)

# ===== 情绪告警 =====
alerts = []
if up_count < 1500 and (pre_up is None or pre_up >= 1500):
    alerts.append("🚨 午盘冰点：涨跌家数跌破1500，主导切1.0，总仓上限5成（单票3成）")
if up_count > 3500 and (pre_up is None or pre_up <= 3500):
    alerts.append("🔴 午盘极度高潮：涨跌家数>3500，切辅助模式，仓位上限2成")
if zt_count > 0 and dt_count > 0 and (dt_count / zt_count) > 0.3:
    alerts.append(f"⚠️ 跌停风险：跌停数/涨停数={dt_count}/{zt_count}={dt_count/zt_count:.1%}>30%")
if up_count < 1500 and up_count > 0 and down_count > 0 and (down_count / up_count) > 2:
    alerts.append(f"⚠️ 情绪恶化：下跌家数/上涨家数={down_count}/{up_count}={down_count/up_count:.1f}倍")

if alerts:
    print("\n🔔 情绪告警：")
    for a in alerts:
        print(f"  {a}")
PYEOF
```

---

## 步骤1.5：盘中新闻快讯（新增！P0-2修复）

> 午间复盘中必须读取上午采集的新闻，并采集上午新出新闻写入【盘中快讯】区

**操作**：
1. **读取已有新闻（去重）**：先读 `trading/news/YYYY-MM-DD.md` 提取已有标题列表
   ```bash
   python3 /Users/yuefengshen/.qclaw/workspace-1gwpiwf3hr163jz5/scripts/news_dedupe.py /Users/yuefengshen/.qclaw/workspace-1gwpiwf3hr163jz5/trading/news/$(date +%Y-%m-%d).md
   ```
2. 读取 `trading/news/YYYY-MM-DD.md` 的全部已有内容（【盘前舆情】+【催化剂相关新闻】），作为上午背景
3. 使用 `tencent-news` 搜索上午（09:30-11:30）新出新闻，关键词：`A股 盘中 快讯`
4. **去重**：将搜索结果与步骤1的已有标题对比，剔除重复条目
5. 将**去重后的新增条目**写入 `trading/news/YYYY-MM-DD.md` 的【盘中快讯】区（如文件不存在先创建）
6. 在后续午间策略分析中引用新闻背景

> ⚡ 此步骤失败不应阻塞后续流程，记录错误后继续。

```bash
python3 << 'PYEOF'
import datetime, os, re

NEWS_FILE = "/Users/yuefengshen/.qclaw/workspace-1gwpiwf3hr163jz5/trading/news/" + datetime.date.today().strftime("%Y-%m-%d") + ".md"

# 1. 读取已有新闻背景
if os.path.exists(NEWS_FILE):
    with open(NEWS_FILE, encoding="utf-8") as f:
        content = f.read()
    print("📰 上午新闻背景：")
    for section in ["盘前舆情", "催化剂相关新闻"]:
        m = re.search(rf"【{section}】(.*?)(?:【|\Z)", content, re.DOTALL)
        if m:
            lines = [l for l in m.group(1).strip().split("\n") if l.strip()]
            print(f"  【{section}】{len(lines)}条")
        else:
            print(f"  【{section}】无")
else:
    print("⚠️ 今日新闻文件不存在，将创建")

# 2. 提示agent调用tencent-news采集上午快讯
print("\n→ 请使用 tencent-news 搜索上午盘中快讯")
print("→ 关键词：A股 盘中 快讯 政策")
print("→ 写入 trading/news/ 的【盘中快讯】区")
print("→ ⚠️ 搜索后先与已有标题去重，只写入新增条目")
PYEOF
```

---

## 步骤2：读取今日竞价选股结果

```bash
# 读取今日最终关注股
cat ~/.qclaw/workspace-1gwpiwf3hr163jz5/trading/关注股.md

# 读取竞价过滤结果
python3 << 'PYEOF'
import json
try:
    with open("/tmp/lobster_bid_result.json") as f:
        result = json.load(f)
    print("=== 今日竞价选股结果 ===")
    for tier, stock in result.get('results', {}).items():
        if stock:
            print(f"{tier}: {stock.get('name')}({stock.get('code')}) 高开{stock.get('change_pct')}% 竞量{stock.get('volume')}手")
        else:
            print(f"{tier}: 无符合规则标的")
except:
    print("⚠️ 竞价结果文件不存在")
PYEOF
```

---

## 步骤3：获取候选股上午表现

```bash
python3 << 'PYEOF'
import subprocess, re, json

# 读取关注股
try:
    with open("/Users/yuefengshen/.qclaw/workspace-1gwpiwf3hr163jz5/trading/关注股.md") as f:
        watch_list = f.read()
except:
    watch_list = ""

# 提取股票代码
codes = re.findall(r'(\d{6})', watch_list)
if not codes:
    print("⚠️ 无关注股")
else:
    # 构造查询字符串
    q_list = []
    for code in codes:
        if code.startswith('6'):
            q_list.append(f"sh{code}")
        else:
            q_list.append(f"sz{code}")
    q_str = ",".join(q_list)
    
    # 获取实时行情
    r = subprocess.run(["curl","-s",f"https://qt.gtimg.cn/q={q_str}"], capture_output=True, timeout=15)
    raw = r.stdout
    for enc in ["gb2312","gbk","utf-8"]:
        try: txt = raw.decode(enc); break
        except: continue
    else: txt = raw.decode("utf-8","replace")
    
    print("=== 关注股上午表现 ===")
    for line in txt.split(";"):
        m = re.search(r'v_(\w+)="([^"]*)"', line)
        if m:
            parts = m.group(2).split("~")
            if len(parts) > 32:
                name = parts[1]
                code = m.group(1)[2:]
                price = parts[4]  # parts[4]=当前价
                pct = parts[32]
                high = parts[33] if len(parts) > 33 else "?"
                low = parts[34] if len(parts) > 34 else "?"
                print(f"{name}({code}): {price}元 ({pct}%) 最高{high} 最低{low}")
PYEOF
```

---

## 步骤4：获取上午涨停池数据

```bash
python3 << 'PYEOF'
import akshare as ak

# 今日涨停股（截至上午）
try:
    zt_pool = ak.stock_zt_pool_em()
    print("=== 今日涨停池（截至11:30）===")
    print(zt_pool[['代码', '名称', '涨停统计', '所属行业', '涨停原因类别']].head(20).to_string())
    
    # 统计板块涨停数
    if '所属行业' in zt_pool.columns:
        sector_counts = zt_pool['所属行业'].value_counts().head(5)
        print("\n=== 板块涨停排名 ===")
        print(sector_counts.to_string())
except Exception as e:
    print(f"获取涨停池失败: {e}")
PYEOF
```

---

## 步骤5：午间重新选股（使用上午实时数据）

> 午间用最新市场数据重跑选股引擎，刷新候选池

```bash
# 重新运行选股引擎（会自动获取最新涨跌家数+涨停池数据）
python3 /Users/yuefengshen/.qclaw/workspace-1gwpiwf3hr163jz5/scripts/lobster_premarket_engine.py

# 读取刷新后的结果
cat /tmp/lobster_premarket_candidates.json
```

**成功标志**：引擎输出「已写入 /tmp/lobster_premarket_candidates.json」

**如果失败**：跳过此步骤，继续用盘前候选池数据执行后续步骤

---

## 步骤5.5：更新买点监控候选池（必做）

> ⚠️ 注意：午间不需要重新跑「竞价过滤」——竞价数据只有09:25才有，11:30没有竞价
> 正确做法：午间重选后，最新候选池已写入 `/tmp/lobster_premarket_candidates.json`
> 买点监控（CRON_BUYPOINT_TASK）会直接读取此文件扫盘中买点（分歧低吸/趋势低吸）
> 09:25的竞价结果（`/tmp/lobster_bid_result.json`）仍然有效，供一进二维度参考

```bash
python3 << 'PYEOF'
import json, os

# 验证候选池已更新
cand_path = '/tmp/lobster_premarket_candidates.json'
if os.path.exists(cand_path):
    with open(cand_path) as f:
        data = json.load(f)
    total = sum(len(v) for v in data.get('candidates', {}).values() if isinstance(v, list))
    print(f"✅ 候选池已更新：{data.get('date')} | 合计{total}只")
    for dim, clist in data.get('candidates', {}).items():
        if clist:
            print(f"  {dim}: {len(clist)}只")
else:
    print("⚠️ 候选池文件不存在，午间重选可能失败")
    exit(1)

# 打印买点监控注意事项
print()
print("📋 下午买点监控说明：")
print("  - 1.0一进二：参考09:25竞价结果（bid_result.json）")
print("  - 1.0分歧低吸/2.0板块卡位/3.0趋势低吸：扫最新候选池盘中买点")
PYEOF
```

**成功标志**：候选池文件存在且日期为今天

**如果失败**：检查步骤5是否正常执行

---

## 步骤6：检查是否需要新增候选股（按规则执行）

> **核心逻辑**：根据上午市场变化，在符合规则的前提下新增下午候选股
> **硬约束**：只能在当前主导维度内新增，不得跨维度

```bash
python3 << 'PYEOF'
import json, subprocess, re, datetime

# 读取午间市场数据
try:
    with open('/tmp/lobster_midday_data.json') as f:
        midday_data = json.load(f)
except:
    print("⚠️ 无法读取午间市场数据")
    exit(1)

up_count = midday_data.get('up_count', 0)
dimension = midday_data.get('dimension', '1.0')
emotion = midday_data.get('emotion', '正常')

print(f"=== 检查是否需要新增候选股 ===")
print(f"当前情绪：{emotion}（涨跌家数{up_count}）")
print(f"主导维度：{dimension}")

# 规则1：冰点或偏弱环境（涨跌家数<1500）→ 不新增
if up_count < 1500:
    print("\n❌ 环境冰点/偏弱，不新增候选股")
    print("策略：维持现有关注股，严控仓位")
    
# 规则2：极度高潮（涨跌家数>3500）→ 不新增（只做辅助）
elif up_count > 3500:
    print("\n❌ 环境极度高潮，不新增候选股")
    print("策略：只关注一字板套利机会，严控仓位")
    
# 规则3：正常环境（1500-2500）→ 可在主导维度内新增
else:
    print(f"\n✅ 环境正常，可在主导维度【{dimension}】内新增")
    
    # 获取上午涨停池
    try:
        import akshare as ak
        zt_pool = ak.stock_zt_pool_em()
        
        # 统计上午最强板块
        if '所属行业' in zt_pool.columns:
            sector_counts = zt_pool['所属行业'].value_counts().head(3)
            print(f"\n上午最强板块：")
            for sector, count in sector_counts.items():
                print(f"  - {sector}: {count}家涨停")
        
        # 根据主导维度筛选新增候选
        new_candidates = []
        
        # 1.0维度：一进二 + 分歧低吸
        if '1.0' in dimension:
            print("\n【1.0维度新增逻辑】")
            
            # 筛选上午首板股（非一字板）
            first_board = zt_pool[zt_pool['涨停统计'] == '1板']
            
            # 排除已关注的股票
            try:
                with open('/Users/yuefengshen/.qclaw/workspace-1gwpiwf3hr163jz5/trading/关注股.md') as f:
                    watch_list = f.read()
            except:
                watch_list = ""
            
            for _, row in first_board.head(10).iterrows():
                code = row['代码']
                name = row['名称']
                
                # 排除已关注
                if code in watch_list or name in watch_list:
                    continue
                
                # 排除一字板（无换手）
                reason = str(row.get('涨停原因类别', ''))
                if '一字' in reason or '开盘涨停' in reason:
                    continue
                
                # 符合条件，加入候选
                new_candidates.append({
                    'tier': '1.0一进二',
                    'name': name,
                    'code': code,
                    'reason': f"上午首板，板块{row.get('所属行业', '未知')}"
                })
                
                if len(new_candidates) >= 2:  # 最多新增2只
                    break
        
        # 2.0维度：板块卡位
        if '2.0' in dimension:
            print("\n【2.0维度新增逻辑】")
            
            # 找到上午爆发板块（≥3家涨停）
            for sector, count in sector_counts.items():
                if count >= 3:
                    # 找该板块涨停股
                    sector_zt = zt_pool[zt_pool['所属行业'] == sector]
                    
                    # 选前排（最早涨停）
                    for _, row in sector_zt.head(3).iterrows():
                        code = row['代码']
                        name = row['名称']
                        
                        if code in watch_list:
                            continue
                        
                        new_candidates.append({
                            'tier': '2.0板块卡位',
                            'name': name,
                            'code': code,
                            'reason': f"{sector}板块爆发，前排涨停"
                        })
                        break  # 每板块只取1只
        
        # 3.0维度：趋势低吸
        if '3.0' in dimension:
            print("\n【3.0维度新增逻辑】")
            
            # 读取趋势池
            try:
                with open('/Users/yuefengshen/.qclaw/workspace-1gwpiwf3hr163jz5/trading/趋势容量池.md') as f:
                    trend_pool = f.read()
            except:
                trend_pool = ""
            
            # 提取趋势池股票代码
            trend_codes = re.findall(r'(\d{6})', trend_pool)
            
            # 检查这些股票上午表现（寻找回踩5日线的）
            for code in trend_codes[:5]:
                if code in watch_list:
                    continue
                
                # 获取实时行情
                q_code = f"sh{code}" if code.startswith('6') else f"sz{code}"
                r = subprocess.run(["curl","-s",f"https://qt.gtimg.cn/q={q_code}"], capture_output=True, timeout=10)
                raw = r.stdout
                for enc in ["gb2312","gbk","utf-8"]:
                    try: txt = raw.decode(enc); break
                    except: continue
                else: txt = raw.decode("utf-8","replace")
                m = re.search(r'v_\w+="([^"]+)"', txt)
                if m:
                    parts = m.group(1).split('~')
                    if len(parts) > 32:
                        name = parts[1]
                        pct = float(parts[32]) if parts[32] else 0
                        
                        # 筛选条件：上午回调但未破5日线
                        if -3 <= pct <= 0:
                            new_candidates.append({
                                'tier': '3.0趋势低吸',
                                'name': name,
                                'code': code,
                                'reason': f"趋势股回调{pct}%，观察5日线支撑"
                            })
                            break
        
        # 输出新增候选
        if new_candidates:
            print(f"\n🔔 关注股变动 | 午间新增 (共{len(new_candidates)}只)")
            print("─" * 30)
            for cand in new_candidates:
                print(f"  ✅ {cand['tier']}: {cand['name']}({cand['code']}) — {cand['reason']}")
            
            # 统计现有关注股总数
            existing = sum(1 for d in watch_data['candidates'].values() if isinstance(d, list) for _ in d) if 'watch_data' in dir() else 0
            print(f"📊 午后关注股合计: 待步骤6.5统计")
            
            # 更新关注股.md（追加）
            with open('/Users/yuefengshen/.qclaw/workspace-1gwpiwf3hr163jz5/trading/关注股.md', 'a') as f:
                f.write(f"\n\n---\n\n## 下午新增候选（{datetime.datetime.now().strftime('%H:%M')}）\n\n")
                for cand in new_candidates:
                    f.write(f"- {cand['name']}({cand['code']}) — {cand['reason']}\n")
            
            print("\n✅ 已追加写入关注股.md")
        else:
            print("\n📋 关注股无变化，午间无符合规则的新增候选")
    
    except Exception as e:
        print(f"\n❌ 获取涨停池失败：{e}")
        print("不新增候选股")
PYEOF
```

---

## 步骤6.5：同步关注股JSON（供买点检测器使用）

```bash
python3 << 'PYEOF'
import json, os, re, datetime

today = datetime.date.today().strftime('%Y-%m-%d')
watch_path = '/tmp/lobster_watchlist_candidates.json'

# 读取现有关注股JSON（09:25写入）或降级盘前
watch_data = None
if os.path.exists(watch_path):
    try:
        with open(watch_path) as f:
            watch_data = json.load(f)
    except:
        pass

if not watch_data or watch_data.get('date') != today:
    try:
        with open('/tmp/lobster_premarket_candidates.json') as f:
            prem = json.load(f)
        watch_data = {
            'date': today, 'source': 'midday_update',
            'emotion': prem.get('emotion', {}),
            'candidates': prem.get('candidates', {})
        }
    except:
        watch_data = {
            'date': today, 'source': 'midday_update',
            'emotion': {}, 'candidates': {}
        }

# 确保维度列表存在
for dim in ['1.0一进二', '1.0分歧低吸', '2.0板块卡位', '3.0趋势低吸']:
    if dim not in watch_data['candidates'] or not isinstance(watch_data['candidates'][dim], list):
        watch_data['candidates'][dim] = []

# 从关注股.md提取午间新增候选
try:
    with open('/Users/yuefengshen/.qclaw/workspace-1gwpiwf3hr163jz5/trading/关注股.md') as f:
        md_content = f.read()
    
    # 查找"下午新增候选"之后的内容
    afternoon_section = md_content.split('下午新增候选')
    if len(afternoon_section) > 1:
        new_lines = afternoon_section[-1]
        new_candidates_raw = re.findall(r'- (.+?)\((\d{6})\) — (.+)', new_lines)
        for name, code, reason in new_candidates_raw:
            # 判断属于哪个维度
            for dim in ['1.0一进二', '1.0分歧低吸', '2.0板块卡位', '3.0趋势低吸']:
                if dim in new_lines[:200]:  # 最近的维度标题
                    existing_codes = {s.get('代码', s.get('code', '')) for s in watch_data['candidates'][dim]}
                    if code not in existing_codes:
                        watch_data['candidates'][dim].append({
                            '代码': code, '名称': name,
                            '来源': '午间新增', '原因': reason
                        })
                    break
            else:
                # 无法判定维度，默认加入分歧低吸
                existing_codes = {s.get('代码', s.get('code', '')) for s in watch_data['candidates']['1.0分歧低吸']}
                if code not in existing_codes:
                    watch_data['candidates']['1.0分歧低吸'].append({
                        '代码': code, '名称': name,
                        '来源': '午间新增', '原因': reason
                    })
    
    # 龙虾聚焦规则：每维度控制上限
    MAX_PER_TIER = {'1.0一进二': 3, '1.0分歧低吸': 3, '2.0板块卡位': 3, '3.0趋势低吸': 5}
    for dim, items in watch_data['candidates'].items():
        max_n = MAX_PER_TIER.get(dim, 3)
        if len(items) > max_n:
            watch_data['candidates'][dim] = items[:max_n]
    
    watch_data['source'] = 'midday_update'
    watch_data['midday_time'] = datetime.datetime.now().strftime('%H:%M')
    
    with open(watch_path, 'w') as f:
        json.dump(watch_data, f, ensure_ascii=False, indent=2)
        print(f"✅ 关注股JSON已同步（维度明细如下）")
        for dim, items in watch_data['candidates'].items():
            print(f"  {dim}: {len(items)}只")
        total = sum(len(items) for items in watch_data['candidates'].values())
        print(f"  合计: {total}只候选股")
except Exception as e:
    print(f"⚠️ 关注股JSON同步失败：{e}")
PYEOF
```

---

## 步骤7：输出午间复盘（禁止预测性表述）

> **必须用"若X则Y"条件应对式，禁止"大概率/应该/可能/预计"**

```markdown
示例输出：

✅ 龙虾午间复盘 YYYY-MM-DD

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📊 情绪面板（11:30）
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
| 指数 | 最新 | 涨幅 | 最高 | 最低 |
|------|------|------|------|------|
| 上证 | XXXX | ±X% | XXXX | XXXX |
| 深证 | XXXX | ±X% | XXXX | XXXX |
| 创业板 | XXXX | ±X% | XXXX | XXXX |

涨跌家数：XXXX涨 XXXX跌 | XX涨停 XX跌停
情绪判定：🚨冰点/⚠️偏弱/✅正常/🔥高潮/🔴极度高潮
情绪变化：📈较盘前+XXX（修复中）/📉较盘前-XXX（恶化中）
主导维度：X.X | 仓位上限：X成
适用策略：打板+分歧低吸 / 板块卡位+高低切 / 只卖不买
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🔔 情绪告警（如有）：
- 🚨 午盘冰点：涨跌家数跌破1500
- 🔴 午盘极度高潮：涨跌家数>3500
- ⚠️ 跌停风险：跌停数/涨停数>30%
- ⚠️ 情绪恶化：下跌家数/上涨家数>2倍
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

【竞价选股上午表现】
- 滨化股份(601678)：高开9.98%，10:15封板，封单3万手
- 中巨芯-U(688549)：高开12.33%，9:45炸板，现涨8.2%
- 杰华特(688141)：低开-1.62%，上午震荡，现跌-2.1%

【下午策略】
- 若涨跌家数回升至>2000 → 维持当前仓位
- 若涨跌家数跌破<1500 → 减仓至3成
- 若滨化股份开板 → 观察封单变化，若封单<1万手则止盈
- 若中巨芯回踩5日线不破 → 可考虑低吸（仓位1成）
- 若杰华特跌破10日线 → 放弃

【下午关注点位】
- 上证支撑位：XXXX  压力位：XXXX
- 创业板支撑位：XXXX  压力位：XXXX
```

---

## 步骤8：发送消息给用户

```bash
# 发送简洁版午间复盘摘要
# message工具发送到元宝
```

---

## 步骤9：IMA同步

```bash
# 将午间复盘写入临时文件
OUTPUT="/tmp/lobster_midday_$(date +%Y-%m-%d).md"

# （agent会将复盘内容写入此文件）

# 调用IMA同步脚本（含重试）
bash ~/.qclaw/workspace-1gwpiwf3hr163jz5/scripts/ima_sync.sh "$OUTPUT" "龙虾午间复盘 $(date +%Y-%m-%d)" 2>>/tmp/ima-errors.log
```

---

## ❌ 错误处理与实时告警

**任何步骤失败，立即发送告警（不等待晚间修复）：**

| 步骤 | 失败表现 | 告警内容 |
|------|---------|----------|
| 读取规则文件 | 文件不存在 | 【CRON_MIDDAY_TASK 告警】规则文件丢失 |
| 获取市场数据 | curl返回空 | 【CRON_MIDDAY_TASK 告警】无法获取市场数据 |
| 读取竞价结果 | 文件不存在 | 【CRON_MIDDAY_TASK 告警】竞价结果丢失 |
| IMA同步 | 返回非0 | 【CRON_MIDDAY_TASK 告警】IMA同步失败 |

**告警方式**：调用 `message` 工具发送到 IMA 知识库「ai自动选股」

---

## ✅ 完成标志

- [ ] 已读取最新规则文件
- [ ] 已获取上午市场数据
- [ ] 已读取竞价选股结果
- [ ] 已分析候选股上午表现
- [ ] 已输出午间复盘（禁止预测性表述）
- [ ] 已同步IMA知识库
- [ ] 已发送消息给用户

---

**任务版本**：v6（午间重选后新增竞价过滤）
**最后更新**：2026-05-25 13:40

---

## 最后步骤：回复用户（必须执行）

> **关键**：你已执行完所有步骤，生成了完整的午间复盘报告
> **必须**：立即回复用户，将午间复盘完整发送给用户
> **禁止**：NO_REPLY、不回复、只写文件不推送
>
> 回复格式：
> ```
> 📊 龙虾午间复盘 YYYY-MM-DD
> 
> [完整的午间复盘内容]
> ```
