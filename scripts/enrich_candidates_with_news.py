#!/usr/bin/env python3
"""候选池新闻与催化注入器 v3
读取候选池JSON + 催化日历.md + 当日memory → 回填到JSON
v3: 防漏校验体系 — 催化完整性校验 + JSON/md双写 + 系统状态写入

防漏机制：
1. 催化日历解析后校验：未决事件总数 vs 扫到7日内事件数，比例过低告警
2. 候选池写入JSON后同步写关注股.md（双写一致性）
3. 系统状态写入催化扫到数，盘中巡检可对比告警
"""

import json, re, datetime, sys
from pathlib import Path

WORKSPACE = Path("/Users/yuefengshen/.qclaw/workspace-1gwpiwf3hr163jz5")
CANDIDATES_FILE = WORKSPACE / "trading" / "premarket_candidates.json"
CATALYST_FILE = WORKSPACE / "trading/催化日历.md"
WATCHLIST_FILE = WORKSPACE / "trading/关注股.md"
SYSTEM_STATE_FILE = WORKSPACE / "trading/系统状态.json"
MEMORY_FILE = WORKSPACE / "memory" / (datetime.date.today().strftime("%Y-%m-%d") + ".md")

# 催化扫描告警阈值：7日内事件数 / 未决事件总数 < 此值则告警
CATALYST_HIT_RATIO_WARN = 0.3

def today_str():
    return datetime.date.today().strftime("%Y-%m-%d")

def load_json():
    if not CANDIDATES_FILE.exists():
        print("⚠️ 候选池文件不存在，跳过")
        return None
    with open(CANDIDATES_FILE, encoding="utf-8") as f:
        return json.load(f)

def parse_catalysts():
    """解析催化日历，返回7日内催化事件列表[(事件名, 赛道, 日期)]
    同时返回全部未决事件数用于完整性校验
    """
    if not CATALYST_FILE.exists():
        return [], 0
    
    today = datetime.date.today()
    deadline = today + datetime.timedelta(days=7)
    
    with open(CATALYST_FILE, encoding="utf-8") as f:
        content = f.read()
    
    # 提取「近期催化事件（未决）」区域，直到下一个##或文件结尾
    idx = content.find("近期催化事件（未决）")
    if idx == -1:
        return [], 0
    next_section = content.find("\n##", idx + 10)
    if next_section == -1:
        snippet = content[idx:]
    else:
        snippet = content[idx:next_section]
    
    # 校验：表格行数
    table_lines = [l for l in snippet.split('\n') if l.strip().startswith('|') and not l.strip().startswith('|---')]
    # 去掉表头行
    data_lines = [l for l in table_lines if '时间' not in l.split('|')[1] if len(l.split('|')) > 2]
    
    events_in_window = []  # 7日内事件
    total_pending = 0       # 全部未决事件数
    
    for line in snippet.split('\n'):
        line = line.strip()
        if not line.startswith('|') or line.startswith('|---'):
            continue
        cols = [c.strip().strip('*') for c in line.split('|') if c.strip()]
        if len(cols) < 4:
            continue
        date_str = cols[0]
        event   = cols[1]
        track   = cols[2]
        status  = cols[3]
        
        # 跳过表头/已兑现/落空
        if status in ('已兑现', '落空', '✅', '❌'):
            continue
        if not date_str or date_str in ('时间', '—'):
            continue
        
        total_pending += 1
        
        # 解析日期（支持多种格式）
        try:
            m = re.search(r'(\d+)月', date_str)
            d_m = re.search(r'(\d+)日', date_str)
            if m and d_m:
                # 「6月16-17日」取第一天
                month, day = int(m.group(1)), int(d_m.group(1))
                year = today.year + 1 if month < today.month else today.year
                event_date = datetime.date(year, month, day)
            elif m:
                # 仅有月份「6月」「7月」→ 当月算7日内，非当月不算
                month = int(m.group(1))
                year = today.year + 1 if month < today.month else today.year
                if year == today.year and month == today.month:
                    # 当月模糊日期 → 视为月底前都可能发生，算7日内
                    event_date = today  # 设为今天，确保落入窗口
                else:
                    # 非当月 → 取月中
                    event_date = datetime.date(year, month, 15)
            else:
                # 无月份（H2 2026/下半年/Q4等）→ 不算7日内
                continue
        except Exception:
            continue
        
        if today <= event_date <= deadline:
            events_in_window.append((event, track, date_str))
    
    return events_in_window, total_pending

def load_radar_map():
    """加载 sector_radar.json 的 active 赛道，将其 tags 作为关键词注入 track_map"""
    radar_file = WORKSPACE / "trading/sector_radar.json"
    extra = {}
    if radar_file.exists():
        try:
            with open(radar_file, encoding="utf-8") as f:
                radar = json.load(f)
            for item in radar.get("active", []):
                name = item["name"]
                tags = item.get("tags", [])
                keywords = [name] + tags
                # 模糊化：取赛道名前4字作为 sector 匹配候选
                sector_hint = name[:4] if len(name) >= 4 else name
                extra[name] = {"keywords": keywords, "sectors": [sector_hint]}
            if extra:
                print(f"  雷达注入：从 sector_radar.json 加载 {len(extra)} 个赛道")
        except Exception as e:
            print(f"  ⚠️ 雷达加载失败: {e}")
    return extra

def match_catalysts_to_candidates(candidates, catalysts):
    """将催化事件匹配到候选股，更新备注
    v3: 基础 track_map + sector_radar.json 动态注入
    """
    # 基础映射（兜底，日历中可能出现但 radar 尚未收录的赛道）
    base_map = {
        "大模型/应用链": {
            "keywords": ["大模型", "AI应用", "腾讯", "DS", "Hy", "人工智能", "智驾", "智能", "AI"],
            "sectors": ["软件开发", "计算机设备", "互联网服务", "游戏", "广告营销", "光学光电", "半导体"],
        },
        "液冷/IDC/DCI": {
            "keywords": ["IDC", "液冷", "算力", "数据中心", "服务器", "温控"],
            "sectors": ["电力", "电网设备", "通信设备"],
        },
        "光通信/存储/光纤": {
            "keywords": ["光通信", "光模块", "光纤", "光芯片", "InP", "激光"],
            "sectors": ["元件", "光学光电", "半导体"],
        },
        "机器人/T链": {
            "keywords": ["机器人", "特斯拉", "工业机器人", "减速器", "伺服"],
            "sectors": ["自动化设备", "汽车零部件", "通用机械"],
        },
        "商业航天": {
            "keywords": ["航天", "SpaceX", "火箭", "卫星"],
            "sectors": ["航天装备", "国防军工", "通信设备"],
        },
        "半导体/芯片": {
            "keywords": ["半导体", "芯片", "晶圆", "封测", "MCU", "存储"],
            "sectors": ["半导体", "元件", "集成电路"],
        },
        "工程机械": {
            "keywords": ["工程机械", "机床", "数控", "挖掘机"],
            "sectors": ["工程机械", "通用机械", "专用设备"],
        },
        # 存储相关子赛道
        "存储/HBM": {
            "keywords": ["存储", "HBM", "DRAM", "NAND"],
            "sectors": ["半导体", "元件", "集成电路"],
        },
        "存储超级周期": {
            "keywords": ["存储", "涨价", "出口"],
            "sectors": ["半导体", "元件"],
        },
        "电力": {
            "keywords": ["电力", "绿电", "用电"],
            "sectors": ["电力", "电网设备"],
        },
    }
    
    # 合并 sector_radar.json 动态赛道（radar 覆盖同名 base 条目）
    track_map = dict(base_map)
    radar_map = load_radar_map()
    for k, v in radar_map.items():
        if k in track_map:
            # 合并 keywords：radar 的 tags 追加到 base 的 keywords
            existing_kw = set(track_map[k].get("keywords", []))
            new_kw = set(v.get("keywords", []))
            track_map[k]["keywords"] = list(existing_kw | new_kw)
        else:
            track_map[k] = v
    
    enriched = 0
    for dim_name, stocks in candidates.items():
        for stock in stocks:
            name = stock.get("名称", "")
            note = stock.get("备注", "")
            sector = stock.get("sector", "") or stock.get("板块", "")
            # 按赛道去重：每个赛道只保留一条（最近的），避免同一股票被同一赛道多个事件重复标注
            track_matched = {}  # {赛道: (date_str, label)}
            
            for event, track, date_str in catalysts:
                mapping = track_map.get(track)
                hit = False
                
                if mapping:
                    if sector and any(s in sector or sector in s for s in mapping["sectors"]):
                        hit = True
                    if not hit:
                        for kw in mapping["keywords"]:
                            if kw in name or kw in note:
                                hit = True
                                break
                else:
                    if sector and (track in sector or sector in track):
                        hit = True
                    elif track[:4] in name:
                        hit = True
                
                if hit:
                    label = f"🔴催化:{date_str}·{track[:6]}"
                    # 同赛道只保留一条（短的date_str通常更近）
                    if track not in track_matched:
                        track_matched[track] = label
            
            if track_matched:
                matched = list(track_matched.values())
                stock["催化"] = matched
                stock["备注"] = " ".join(matched) + " | " + note if note else " ".join(matched)
                enriched += 1
    
    return enriched

def parse_news_sentiment():
    """从 trading/news/YYYY-MM-DD.md 的【盘前舆情】区提取舆情"""
    NEWS_FILE = WORKSPACE / "trading/news" / (datetime.date.today().strftime("%Y-%m-%d") + ".md")
    if not NEWS_FILE.exists():
        if MEMORY_FILE.exists():
            with open(MEMORY_FILE, encoding="utf-8") as f:
                content = f.read()
            match = re.search(r"## 舆情速报.*?\n(.+?)(?:## |\n\n|\Z)", content, re.DOTALL)
            if match:
                text = match.group(1).strip()[:500]
                return text if text else None
        return None
    
    with open(NEWS_FILE, encoding="utf-8") as f:
        content = f.read()
    
    match = re.search(r"【盘前舆情】(.*?)(?:【|\Z)", content, re.DOTALL)
    sentiment_parts = []
    if match:
        text = match.group(1).strip()
        if text and len(text) > 10:
            sentiment_parts.append("盘前舆情:\n" + text[:600])
    
    match2 = re.search(r"【催化剂相关新闻】(.*?)(?:【|\Z)", content, re.DOTALL)
    if match2:
        text2 = match2.group(1).strip()
        if text2 and len(text2) > 10:
            sentiment_parts.append("催化相关:\n" + text2[:400])
    
    if sentiment_parts:
        return "\n\n---\n\n".join(sentiment_parts)
    return None

def sync_watchlist_md(candidates):
    """候选池JSON → 关注股.md 双写
    确保JSON和md内容一致，防止单点丢失
    """
    lines = [f"# 关注股 {today_str()}", "", "## 候选池（盘前版）", ""]
    
    dim_order = ["1.0一进二", "1.0分歧低吸", "2.0板块卡位", "3.0趋势低吸"]
    for dim in dim_order:
        stocks = candidates.get(dim, [])
        if not stocks:
            continue
        lines.append(f"### {dim}")
        for s in stocks:
            name = s.get("名称", "?")
            code = s.get("代码", "")
            note = s.get("备注", "")
            催化 = s.get("催化", [])
            note_part = f" — {note}" if note else ""
            催化_part = f" [{' '.join(催化)}]" if 催化 else ""
            lines.append(f"- {name}({code}){note_part}{催化_part}")
        lines.append("")
    
    with open(WATCHLIST_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"  双写：关注股.md 已同步 ({len(lines)}行)")

def update_system_state(catalysts_in_window, total_pending, enriched_count):
    """将催化扫描结果写入系统状态文件，供盘中巡检对比"""
    state = {}
    if SYSTEM_STATE_FILE.exists():
        try:
            with open(SYSTEM_STATE_FILE, encoding="utf-8") as f:
                state = json.load(f)
        except:
            state = {}
    
    state["catalyst_scan"] = {
        "date": today_str(),
        "events_in_window": catalysts_in_window,  # 7日内事件数
        "total_pending": total_pending,            # 日历未决事件总数
        "enriched_stocks": enriched_count,         # 匹配到催化的候选股数
    }
    state["last_updated"] = today_str()
    
    with open(SYSTEM_STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)

def main():
    print("→ 候选池新闻与催化注入器 v3")
    
    data = load_json()
    if not data:
        return
    
    # 1. 解析催化日历（含完整性校验）
    catalysts, total_pending = parse_catalysts()
    print(f"  催化：找到{len(catalysts)}个7日内事件（日历未决{total_pending}个）")
    for e, t, d in catalysts:
        print(f"    [{d}] {e} → {t}")
    
    # 完整性校验：7日内事件数 / 未决总数 过低则告警
    if total_pending > 0:
        hit_ratio = len(catalysts) / total_pending
        if hit_ratio < CATALYST_HIT_RATIO_WARN:
            print(f"  ⚠️ 催化完整性告警：7日内{len(catalysts)}/{total_pending}未决({hit_ratio:.0%} < {CATALYST_HIT_RATIO_WARN:.0%}阈值)，可能存在截断或日期解析错误")
        else:
            print(f"  ✅ 催化完整性校验通过：{len(catalysts)}/{total_pending}未决({hit_ratio:.0%})")
    elif total_pending == 0:
        print(f"  ⚠️ 催化日历无未决事件，可能文件被清空或解析失败")
    
    # 2. 匹配到候选股
    candidates = data.get("candidates", {})
    enriched_count = match_catalysts_to_candidates(candidates, catalysts)
    print(f"  注入：{enriched_count}只候选股已附加催化标注")
    
    # 3. 读舆情速报
    sentiment = parse_news_sentiment()
    if sentiment:
        data["news_sentiment"] = sentiment
        print(f"  舆情：已写入JSON ({len(sentiment)}字)")
    else:
        data["news_sentiment"] = None
        print("  舆情：无舆情速报")
    
    # 4. 写回JSON
    with open(CANDIDATES_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    
    # 5. 双写关注股.md
    if candidates:
        sync_watchlist_md(candidates)
    
    # 6. 系统状态写入（供盘中巡检对比）
    update_system_state(len(catalysts), total_pending, enriched_count)
    print(f"  状态：系统状态.json 已更新（催化扫描{len(catalysts)}/{total_pending}）")
    
    print(f"✅ 候选池已更新：{CANDIDATES_FILE}")

if __name__ == "__main__":
    main()
