#!/usr/bin/env python3
"""
更新持仓标的实时价格
读取trading/模拟持仓.json,用腾讯API获取最新价格,更新current_price和market_value
"""
import json, subprocess, re, sys
from pathlib import Path

WS = Path(__file__).parent.parent
POS_FILE = WS / "trading/模拟持仓.json"

def update_position_prices():
    """更新持仓实时价格"""
    if not POS_FILE.exists():
        print("❌ 模拟持仓.json不存在")
        return

    pos = json.loads(POS_FILE.read_text())
    positions = pos.get('positions', [])
    if not positions:
        print("📭 无持仓,跳过价格更新")
        return

    # 获取所有持仓代码
    codes = []
    for s in positions:
        code = s['code']
        prefix = 'sh' if code.startswith('6') else 'sz'
        codes.append(prefix + code)

    # 批量获取实时行情
    url = f"https://qt.gtimg.cn/q={','.join(codes)}"
    r = subprocess.run(['curl', '-s', '-L', '--max-time', '10', '-A', 'Mozilla/5.0', url],
                       capture_output=True)
    text = r.stdout.decode('gbk', errors='ignore')

    # 解析行情
    price_map = {}
    for line in text.strip().split('\n'):
        if not line.startswith('v_'):
            continue
        try:
            parts = line.split('~')
            if len(parts) < 33:
                continue
            code_raw = parts[0]
            code = code_raw.split('=')[0].replace('v_', '')
            current_price = float(parts[3])  # 现价
            price_map[code] = current_price
        except:
            continue

    # 更新持仓（含浮动盈亏重算）
    updated = 0
    for s in positions:
        code = s['code']
        prefix = 'sh' if code.startswith('6') else 'sz'
        code_prefixed = prefix + code
        if code_prefixed in price_map:
            s['current_price'] = price_map[code_prefixed]
            s['market_value'] = round(s['shares'] * s['current_price'], 2)
            # 重算浮动盈亏
            cost = s.get('cost', 0)
            if cost > 0 and s['shares'] > 0:
                s['floating_pnl'] = round(s['market_value'] - cost, 2)
                s['floating_pnl_pct'] = round(s['floating_pnl'] / cost * 100, 2)
            updated += 1

    # 更新capital中的market_value和浮动盈亏
    total_mv = sum(s.get('market_value', 0) for s in positions)
    total_cost = sum(s.get('cost', 0) for s in positions)
    floating_pnl = round(total_mv - total_cost, 2)
    pos['capital']['market_value'] = total_mv
    pos['capital']['floating_pnl'] = floating_pnl
    # 兼容 available 或 available_cash 两种键名
    available = pos['capital'].get('available', pos['capital'].get('available_cash', 0))
    pos['capital']['total_assets'] = round(available + total_mv, 2)
    # 同步total字段
    pos['capital']['total'] = pos['capital']['total_assets']

    POS_FILE.write_text(json.dumps(pos, ensure_ascii=False, indent=2))
    print(f"✅ 已更新 {updated} 只持仓价格")

if __name__ == '__main__':
    update_position_prices()
