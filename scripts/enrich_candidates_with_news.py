#!/usr/bin/env python3
"""候选池新闻与催化注入器 v2
读取候选池JSON + 催化日历.md + 当日memory → 回填到JSON
在步骤1(选股引擎)和步骤2(格式化发送)之间调用
v2: 修复赛道匹配Bug — 去掉kw in track自匹配，增加sector交叉匹配
"""

import json, re, datetime, sys
from pathlib import Path

WORKSPACE = Path("/Users/yuefengshen/.qclaw/workspace-1gwpiwf3hr163jz5")
CANDIDATES_FILE = Path("/tmp/lobster_premarket_candidates.json")
CATALYST_FILE = WORKSPACE / "trading/催化日历.md"
# 动态日期，不再硬编码2026-05-22
MEMORY_FILE = WORKSPACE / "memory" / (datetime.date.today().strftime("%Y-%m-%d") + ".md")

def today_str():
    return datetime.date.today().strftime("%Y-%m-%d")

def load_json():
    if not CANDIDATES_FILE.exists():
        print("⚠️ 候选池文件不存在，跳过")
        return None
    with open(CANDIDATES_FILE, encoding="utf-8") as f:
        return json.load(f)

def parse_catalysts():
    """解析催化日历，返回7日内催化事件列表[(事件名, 赛道, 日期)]"""
    if not CATALYST_FILE.exists():
        return []
    
    today = datetime.date.today()
    deadline = today + datetime.timedelta(days=7)
    
    with open(CATALYST_FILE, encoding="utf-8") as f:
        content = f.read()
    
    # 提取近期催化表格（跳过markdown分隔符+表头行）
    idx = content.find("近期催化事件（未决）")
    snippet = content[idx:idx+1000]
    
    events = []
    rows = re.findall(r'\|(.+?)\|(.+?)\|(.+?)\|(.+?)\|', snippet)
    for row in rows:
        date_str = row[0].strip().strip('*')
        event = row[1].strip().strip('*')
        track = row[2].strip().strip('*')
        status = row[3].strip().strip('*')
        
        # 跳过表头/分隔符/已兑现
        if status in ('已兑现', '落空', '✅', '❌'):
            continue
        if not date_str or date_str in ('时间', '—') or '------' in date_str:
            continue
        
        # 解析日期
        try:
            m = re.search(r'(\d+)月', date_str)
            d_m = re.search(r'(\d+)日', date_str)
            if m and d_m:
                month, day = int(m.group(1)), int(d_m.group(1))
                event_date = datetime.date(today.year, month, day)
            elif m:
                month = int(m.group(1))
                event_date = datetime.date(today.year, month, 15)  # 月份中间
            else:
                continue
        except:
            continue
        
        if today <= event_date <= deadline:
            events.append((event, track, date_str))
    
    return events

def match_catalysts_to_candidates(candidates, catalysts):
    """将催化事件匹配到候选股，更新备注
    v2: 基于sector交叉匹配，不再用kw in track自匹配
    """
    # 赛道关键词映射 — keywords用于匹配候选股名称/备注，sectors用于精确匹配sector字段
    track_map = {
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
    }
    
    enriched = 0
    for dim_name, stocks in candidates.items():
        for stock in stocks:
            name = stock.get("名称", "")
            note = stock.get("备注", "")
            sector = stock.get("sector", "") or stock.get("板块", "")
            matched = []
            
            for event, track, date_str in catalysts:
                mapping = track_map.get(track)
                hit = False
                
                if mapping:
                    # 精确匹配：候选股sector在催化受益sector列表中
                    if sector and any(s in sector or sector in s for s in mapping["sectors"]):
                        hit = True
                    # 模糊匹配：关键词出现在股票名称或备注中（不匹配track本身）
                    if not hit:
                        for kw in mapping["keywords"]:
                            if kw in name or kw in note:
                                hit = True
                                break
                else:
                    # 未知赛道：仅用赛道名做模糊匹配（严格模式）
                    if sector and (track in sector or sector in track):
                        hit = True
                    elif track[:4] in name:
                        hit = True
                
                if hit:
                    matched.append(f"🔴催化:{date_str}·{track[:6]}")
            
            if matched:
                stock["催化"] = matched
                stock["备注"] = " ".join(matched) + " | " + note if note else " ".join(matched)
                enriched += 1
    
    return enriched

def parse_news_sentiment():
    """从 trading/news/YYYY-MM-DD.md 的【盘前舆情】区提取舆情
    v3: 改读 trading/news/ 而非 memory/ （修复P0-1断链）
    """
    NEWS_FILE = WORKSPACE / "trading/news" / (datetime.date.today().strftime("%Y-%m-%d") + ".md")
    if not NEWS_FILE.exists():
        # fallback: 尝试从 memory/ 读取（兼容旧逻辑）
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
    
    # 提取【盘前舆情】区
    match = re.search(r"【盘前舆情】(.*?)(?:【|\Z)", content, re.DOTALL)
    sentiment_parts = []
    if match:
        text = match.group(1).strip()
        if text and len(text) > 10:
            sentiment_parts.append("盘前舆情:\n" + text[:600])
    
    # 同时提取【催化剂相关新闻】区（如有）
    match2 = re.search(r"【催化剂相关新闻】(.*?)(?:【|\Z)", content, re.DOTALL)
    if match2:
        text2 = match2.group(1).strip()
        if text2 and len(text2) > 10:
            sentiment_parts.append("催化相关:\n" + text2[:400])
    
    if sentiment_parts:
        return "\n\n---\n\n".join(sentiment_parts)
    return None

def main():
    print("→ 候选池新闻与催化注入器 v2")
    
    data = load_json()
    if not data:
        return
    
    # 1. 解析催化日历
    catalysts = parse_catalysts()
    print(f"  催化：找到{len(catalysts)}个7日内事件")
    for e, t, d in catalysts:
        print(f"    [{d}] {e} → {t}")
    
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
    
    print(f"✅ 候选池已更新：{CANDIDATES_FILE}")

if __name__ == "__main__":
    main()
