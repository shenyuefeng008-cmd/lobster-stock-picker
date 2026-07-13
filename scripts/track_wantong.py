#!/usr/bin/env python3
"""
万通发展（600246）长期跟踪脚本
每次运行获取实时行情，更新 long_term_watchlist.json，如有异动则推送告警
"""
import json
import subprocess
import re
from datetime import datetime

WATCHLIST_FILE = "/Users/yuefengshen/.qclaw/workspace-1gwpiwf3hr163jz5/trading/long_term_watchlist.json"
STOCK_CODE = "sh600246"
STOCK_NAME = "万通发展"

def get_realtime_quote():
    """获取腾讯行情API实时数据"""
    try:
        result = subprocess.run(["curl", "-s", f"https://qt.gtimg.cn/q={STOCK_CODE}"],
                                capture_output=True, timeout=15)
        content = result.stdout.decode('gbk', errors='replace').strip()
        
        # 解析 v_sh600246="..." 格式
        match = re.search(r'="(.+)"', content)
        if not match:
            return None
        
        fields = match.group(1).split('~')
        return {
            'name': fields[1],
            'code': fields[2],
            'price': float(fields[3]),
            'last_close': float(fields[4]),
            'open': float(fields[5]),
            'volume': int(fields[6]),
            'bid_vol': int(fields[7]),
            'ask_vol': int(fields[8]),
            'high': float(fields[33]) if len(fields) > 33 else float(fields[3]),
            'low': float(fields[34]) if len(fields) > 34 else float(fields[3]),
            'change_pct': float(fields[32]) if len(fields) > 32 else 0.0,
            'amount': float(fields[37]) if len(fields) > 37 else 0.0,
            'bid1': float(fields[9]),
            'bid1_vol': int(fields[10]),
            'time': fields[30] if len(fields) > 30 else datetime.now().strftime("%Y%m%d%H%M%S")
        }
    except Exception as e:
        print(f"❌ 获取行情失败: {e}")
        return None

def load_watchlist():
    """加载关注列表"""
    try:
        with open(WATCHLIST_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except:
        return {"stocks": [], "last_updated": ""}

def save_watchlist(data):
    """保存关注列表"""
    data['last_updated'] = datetime.now().strftime("%Y-%m-%d %H:%M")
    with open(WATCHLIST_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def check_alerts(stock_info, history):
    """检查告警条件"""
    alerts = []
    
    # 1. 涨跌超过5%告警
    if abs(stock_info['change_pct']) >= 5.0:
        alerts.append(f"📈 涨跌异动：{stock_info['change_pct']:+.2f}%")
    
    # 2. 涨停/跌停告警
    if stock_info['price'] == stock_info['high'] and stock_info['change_pct'] > 9.5:
        alerts.append("🔴 涨停！")
    elif stock_info['price'] == stock_info['low'] and stock_info['change_pct'] < -9.5:
        alerts.append("🟢 跌停！")
    
    # 3. 与前一日对比涨跌幅
    if history:
        last_close = history[-1].get('price', stock_info['last_close'])
        price_change = (stock_info['price'] - last_close) / last_close * 100
        if abs(price_change) >= 5.0:
            alerts.append(f"⚠️ 较上次跟踪涨跌：{price_change:+.2f}%")
    
    return alerts

def update_watchlist(quote):
    """更新关注列表"""
    data = load_watchlist()
    
    # 查找或创建万通发展记录
    stock_record = None
    for stock in data['stocks']:
        if stock['code'] == '600246':
            stock_record = stock
            break
    
    if not stock_record:
        stock_record = {
            "code": "600246",
            "name": "万通发展",
            "added_date": datetime.now().strftime("%Y-%m-%d"),
            "added_time": datetime.now().strftime("%H:%M"),
            "added_price": quote['price'],
            "added_reason": "用户要求长期跟踪",
            "alert_conditions": {
                "price_change_alert_pct": 5.0,
                "volume_surge_ratio": 2.0,
                "limit_up_down_alert": True
            },
            "notes": "房地产+资产重组概念",
            "track_history": []
        }
        data['stocks'].append(stock_record)
    
    # 添加今日跟踪记录
    today = datetime.now().strftime("%Y-%m-%d")
    time_now = datetime.now().strftime("%H:%M")
    
    # 避免重复记录（同一天只记录一次）
    if stock_record['track_history'] and stock_record['track_history'][-1]['date'] == today:
        # 更新今日记录
        stock_record['track_history'][-1] = {
            "date": today,
            "time": time_now,
            "price": quote['price'],
            "change_pct": quote['change_pct'],
            "volume": quote['volume'],
            "amount": quote['amount'],
            "high": quote['high'],
            "low": quote['low'],
            "note": f"涨停" if quote['change_pct'] > 9.5 else ""
        }
    else:
        # 新增记录
        stock_record['track_history'].append({
            "date": today,
            "time": time_now,
            "price": quote['price'],
            "change_pct": quote['change_pct'],
            "volume": quote['volume'],
            "amount": quote['amount'],
            "high": quote['high'],
            "low": quote['low'],
            "note": f"涨停" if quote['change_pct'] > 9.5 else ""
        })
    
    # 保留最近30条记录
    stock_record['track_history'] = stock_record['track_history'][-30:]
    
    save_watchlist(data)
    return stock_record

def main():
    print(f"🔍 开始跟踪 {STOCK_NAME}（600246）...")
    
    # 获取实时行情
    quote = get_realtime_quote()
    if not quote:
        print("❌ 获取行情失败")
        return
    
    print(f"📊 实时行情（{quote['time']}）：")
    print(f"  现价：{quote['price']:.2f}（昨收{quote['last_close']:.2f}）")
    print(f"  涨跌：{quote['change_pct']:+.2f}%")
    print(f"  开盘：{quote['open']:.2f} | 最高：{quote['high']:.2f} | 最低：{quote['low']:.2f}")
    print(f"  成交量：{quote['volume']/10000:.2f}万手 | 成交额：{quote['amount']/100000000:.2f}亿元")
    
    # 更新关注列表
    stock_record = update_watchlist(quote)
    
    # 检查告警
    alerts = check_alerts(quote, stock_record['track_history'])
    
    if alerts:
        print(f"\n⚠️ 告警：")
        for alert in alerts:
            print(f"  {alert}")
    else:
        print(f"\n✅ 无异常波动")
    
    print(f"\n✅ 跟踪记录已更新：{WATCHLIST_FILE}")

if __name__ == "__main__":
    main()
