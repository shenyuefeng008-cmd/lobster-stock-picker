"""
龙虾自动交易决策引擎
根据规则自动判断买卖时机
"""
import json, subprocess, re, datetime, sys
from pathlib import Path

BASE = Path(__file__).parent
CONFIG_FILE = Path(__file__).parent.parent / "lobster-config.json"

def load_config():
    with open(CONFIG_FILE) as f:
        return json.load(f)

def get_realtime_quotes(codes):
    """批量获取实时行情"""
    ql = [f"sh{c}" if c.startswith('6') else f"sz{c}" for c in codes]
    r = subprocess.run(["curl","-s","--max-time","10",f"https://qt.gtimg.cn/q={','.join(ql)}"], capture_output=True, timeout=12)
    for enc in ["gb2312","gbk","utf-8"]:
        try: txt = r.stdout.decode(enc); break
        except: continue
    
    quotes = {}
    for line in txt.split(";"):
        m = re.search(r'v_(\w+)="([^"]*)"', line)
        if m:
            p = m.group(2).split("~")
            if len(p) > 37:
                code = p[2]
                quotes[code] = {
                    "name": p[1],
                    "price": float(p[4]),  # p[4]=当前价, p[3]=昨收
                    "pct": float(p[32]),
                    "vol": float(p[36]),
                    "amount": float(p[37]) if len(p) > 37 else 0
                }
    return quotes

def get_market_data():
    """获取市场情绪数据"""
    # 涨跌家数
    r = subprocess.run(["curl","-s","-L","--max-time","10","-A","Mozilla/5.0","https://legulegu.com/stockdata/market-activity"], capture_output=True, text=True, timeout=12)
    m = re.search(r'content="(2026-[^"]+)"', r.stdout)
    emo_text = m.group(1) if m else ""
    
    mu = re.search(r'(\d+)家上涨', emo_text)
    md = re.search(r'(\d+)家下跌', emo_text)
    up = int(mu.group(1)) if mu else 0
    down = int(md.group(1)) if md else 0
    
    return {"up": up, "down": down, "total": up + down}

def get_position_limits(up_count):
    """根据情绪返回仓位上限和主导维度"""
    if up_count < 1500:
        return {"limit": 5, "dimension": "1.0", "reason": "冰点"}
    elif up_count < 2500:
        return {"limit": 9, "dimension": "1.0+3.0", "reason": "正常"}
    elif up_count < 3500:
        return {"limit": 7, "dimension": "2.0+1.0", "reason": "高潮"}
    else:
        return {"limit": 2, "dimension": "辅助", "reason": "极度高潮"}

# ========== 买点判断 ==========
def check_buy_signals(candidates, quotes, market_data):
    """检查候选股的买点信号"""
    config = load_config()
    up_count = market_data["up"]
    limits = get_position_limits(up_count)
    
    signals = []
    
    for dim, stocks in candidates.get("candidates", {}).items():
        for s in stocks:
            code = s.get("代码") or s.get("code")
            name = s.get("名称") or s.get("name")
            q = quotes.get(code)
            
            if not q:
                continue
            
            pct = q["pct"]
            price = q["price"]
            vol = q["vol"]
            
            signal = {"code": code, "name": name, "dimension": dim, "price": price, "pct": pct}
            
            # 1.0一进二判断
            if "一进二" in dim:
                # 涨幅3-10%，量比健康
                if 3 <= pct <= 10:
                    signal["action"] = "BUY"
                    signal["pct_position"] = 10  # 一进二轻仓
                    signal["reason"] = "一进二形态"
                    signals.append(signal)
            
            # 1.0分歧低吸判断
            elif "分歧低吸" in dim:
                # 涨幅0~+3%，未大涨
                if 0 <= pct <= 3:
                    signal["action"] = "BUY"
                    signal["pct_position"] = 20  # 分歧低吸稍重
                    signal["reason"] = "分歧低吸，回调均线支撑"
                    signals.append(signal)
            
            # 2.0板块卡位判断
            elif "板块卡位" in dim:
                # 涨幅2-8%，板块有跟风
                if 2 <= pct <= 8:
                    signal["action"] = "BUY"
                    signal["pct_position"] = 15
                    signal["reason"] = "板块卡位，前排领涨"
                    signals.append(signal)
    
    # 按涨幅排序，强股优先
    signals.sort(key=lambda x: x["pct"], reverse=True)
    
    # 应用仓位限制
    max_positions = 8
    current_positions = 4  # TODO: 从模拟持仓读取
    
    result = []
    for s in signals:
        if len(result) >= max_positions:
            break
        if limits["limit"] > 0:
            result.append(s)
    
    return {
        "market": {"up": up_count, "limits": limits},
        "signals": result
    }

# ========== 卖点判断 ==========
def check_sell_signals(positions, quotes):
    """检查持仓股的卖点信号"""
    signals = []
    
    for p in positions:
        code = p["code"]
        name = p["name"]
        buy_price = p["buy_price"]
        shares = p["shares"]
        dimension = p.get("dimension", "")
        
        q = quotes.get(code)
        if not q:
            continue
        
        current_price = q["price"]
        pct = q["pct"]
        
        # 计算盈亏
        pnl_pct = (current_price - buy_price) / buy_price * 100
        
        signal = {"code": code, "name": name, "buy_price": buy_price, "current_price": current_price, "pnl_pct": pnl_pct}
        
        # 1. 止盈判断
        if pnl_pct >= 25:
            signal["action"] = "SELL_ALL"
            signal["reason"] = "止盈25%清仓"
            signals.append(signal)
        elif pnl_pct >= 15 and not p.get("profit_taken", 0):
            signal["action"] = "SELL_HALF"
            signal["reason"] = "止盈15%减半仓"
            signals.append(signal)
        
        # 2. 止损判断
        elif pnl_pct <= -8:
            signal["action"] = "SELL_ALL"
            signal["reason"] = "止损-8%清仓"
            signals.append(signal)
        
        # 3. 硬止损（收盘价<MA10）- 需要K线数据，暂时跳过
    
    return signals

# ========== 主决策 ==========
def make_decision():
    """执行完整决策流程"""
    print("=" * 60)
    print(f"🧠 自动交易决策 {datetime.datetime.now().strftime('%H:%M:%S')}")
    print("=" * 60)
    
    # 1. 获取市场情绪
    market = get_market_data()
    limits = get_position_limits(market["up"])
    print(f"\n📊 情绪: {market['up']}家上涨 → {limits['dimension']}主导，仓位上限{limits['limit']}成")
    
    # 2. 读取候选股
    candidates_file = Path("/tmp/lobster_premarket_candidates.json")
    if not candidates_file.exists():
        print("⚠️ 无候选股文件")
        return
    
    with open(candidates_file) as f:
        candidates = json.load(f)
    
    # 3. 获取实时行情
    all_codes = []
    for dim, stocks in candidates.get("candidates", {}).items():
        for s in stocks:
            code = s.get("代码") or s.get("code")
            if code:
                all_codes.append(code)
    
    quotes = get_realtime_quotes(all_codes)
    
    # 4. 检查买点信号
    buy_signals = check_buy_signals(candidates, quotes, market)
    print(f"\n📈 买点信号: {len(buy_signals['signals'])}只")
    for s in buy_signals["signals"][:3]:
        print(f"  ✓ {s['name']}({s['code']}) {s['pct']:+.2f}% [{s['dimension']}] {s['reason']}")
    
    # 5. 检查卖点信号
    sys.path.insert(0, str(BASE))
    from simulated_trading import _load
    
    data = _load()
    positions = data.get("positions", [])
    
    if positions:
        sell_signals = check_sell_signals(positions, quotes)
        print(f"\n📉 卖点信号: {len(sell_signals)}只")
        for s in sell_signals:
            print(f"  ⚠️ {s['name']}({s['code']}) {s['pnl_pct']:+.2f}% → {s['reason']}")
    else:
        print("\n📦 无持仓")
    
    print("\n" + "=" * 60)
    return {
        "market": market,
        "buy_signals": buy_signals,
        "sell_signals": sell_signals if positions else []
    }

if __name__ == "__main__":
    make_decision()


# ========== 自动执行 ==========
def auto_execute(decisions):
    """根据决策自动执行买卖"""
    import sys
    sys.path.insert(0, str(BASE))
    from simulated_trading import buy, sell, sell_partial, _load
    
    # 检查交易时段
    from simulated_trading import is_trading_hours
    in_trading, status = is_trading_hours()
    if not in_trading:
        return f"非交易时段({status})，跳过自动执行"
    
    results = []
    data = _load()
    positions = data.get("positions", [])
    
    # 1. 执行卖出（先检查持仓）
    for s in decisions.get("sell_signals", []):
        code = s["code"]
        name = s["name"]
        act = s["action"]
        
        # 检查是否在场
        在场 = any(p["code"] == code for p in positions)
        if not 在场:
            continue
        
        if act == "SELL_ALL":
            # 获取当前价
            q = get_realtime_quotes([code]).get(code, {})
            if q:
                r = sell(code, q["price"], s["reason"], s.get("reason", "止损"))
                results.append(r)
        elif act == "SELL_HALF":
            q = get_realtime_quotes([code]).get(code, {})
            if q:
                r = sell_partial(code, 50, q["price"], s["reason"], "止盈")
                results.append(r)
    
    # 2. 执行买入
    for b in decisions.get("buy_signals", {}).get("signals", [])[:2]:  # 最多2只
        code = b["code"]
        name = b["name"]
        pct_pos = b.get("pct_position", 10)
        
        # 检查是否已有持仓
        if any(p["code"] == code for p in positions):
            continue
        
        # 获取当前价
        q = get_realtime_quotes([code]).get(code, {})
        if q:
            r = buy(code, name, q["price"], b.get("reason", ""), b.get("dimension", ""), position_pct=pct_pos)
            if "禁止" not in r:  # 排除非交易时段等拒绝
                results.append(r)
    
    return "\n".join(results) if results else "无自动执行"

