#!/usr/bin/env python3
"""
龙虾交易系统 · 资金账本自动复核脚本
每天15:30收盘后执行，核验capital字段准确性，发现差异自动修正并记录
"""

import json, sys
from pathlib import Path
from datetime import datetime

BASE = Path(__file__).resolve().parent.parent / "trading"
POSITION_FILE = BASE / "模拟持仓.json"
AUDIT_LOG = BASE / f"capital_audit_{datetime.now().strftime('%Y%m%d')}.log"

def log(msg):
    ts = datetime.now().strftime('%H:%M:%S')
    line = f"[{ts}] {msg}"
    print(line)
    with open(AUDIT_LOG, 'a') as f:
        f.write(line + '\n')

def calc_fees(price, shares, is_buy):
    amount = price * shares
    commission = max(amount * 0.00025, 5)
    if is_buy:
        return commission
    else:
        stamp = amount * 0.001
        return commission + stamp

def validate_and_fix():
    log("=== 资金账本自动复核开始 ===")
    
    if not POSITION_FILE.exists():
        log("ERROR: 模拟持仓.json 不存在")
        return
    
    d = json.load(open(POSITION_FILE))
    trades = d.get('trade_log', [])
    positions = d.get('positions', [])
    
    # 1. 核验透支卖出
    log("--- 检查透支卖出 ---")
    bal = {}
    overdraft_found = False
    for t in trades:
        code = t['code']
        if t['type'] == 'BUY':
            bal[code] = bal.get(code, 0) + t['shares']
        elif t['type'] == 'SELL':
            bal[code] = bal.get(code, 0) - t['shares']
            if bal[code] < 0:
                log(f"  ❌ 透支 {t['name']}({code}) {t['date']} SELL {t['shares']}股 透支{-bal[code]}股")
                overdraft_found = True
    
    if not overdraft_found:
        log("  ✅ 无透支卖出")
    
    # 2. 逐笔FIFO计算可用现金
    log("--- 计算可用现金 ---")
    cash = 1000000.0
    fifo_positions = {}
    realized_pnl = 0
    
    for t in trades:
        code = t['code']
        if t['type'] == 'BUY':
            fee = calc_fees(t['price'], t['shares'], True)
            cash -= (t['price'] * t['shares'] + fee)
            if code not in fifo_positions:
                fifo_positions[code] = []
            fifo_positions[code].append((t['shares'], t['price']))
        elif t['type'] == 'SELL':
            remaining = t['shares']
            total_cost = 0
            while remaining > 0 and fifo_positions.get(code):
                s, p = fifo_positions[code][0]
                match = min(remaining, s)
                total_cost += match * p
                remaining -= match
                if match >= s:
                    fifo_positions[code].pop(0)
                else:
                    fifo_positions[code][0] = (s - match, p)
            
            sell_revenue = t['shares'] * t['price']
            sell_fee = calc_fees(t['price'], t['shares'], False)
            cash += (sell_revenue - sell_fee)
            pnl = sell_revenue - sell_fee - total_cost
            realized_pnl += pnl
    
    log(f"  逐笔FIFO可用现金: {cash:,.2f}")
    
    # 3. 计算持仓市值
    log("--- 计算持仓市值 ---")
    market_value = 0
    pos_total_pnl = 0
    for p in positions:
        mv = p.get('market_value', 0)
        market_value += mv
        fp = p.get('total_pnl', 0)
        pos_total_pnl += fp
        log(f"  {p['name']}({p['code']}) {p['shares']}股 现价{p.get('current_price','?')} 市值{mv} 浮盈{fp}")
    
    log(f"  持仓市值合计: {market_value:,.2f}")
    
    # 4. 对比capital字段
    log("--- 对比capital字段 ---")
    cap = d.get('capital', {})
    errors = []
    
    calc_total = cash + market_value
    file_total = cap.get('total_assets', 0)
    if abs(calc_total - file_total) > 100:
        errors.append(f"total_assets 差异: 计算={calc_total:,.2f} 文件={file_total:,.2f} 差={calc_total-file_total:,.2f}")
    
    calc_avail = round(cash, 2)
    file_avail = cap.get('available', 0)
    if abs(calc_avail - file_avail) > 100:
        errors.append(f"available 差异: 计算={calc_avail:,.2f} 文件={file_avail:,.2f} 差={calc_avail-file_avail:,.2f}")
    
    calc_hist_pnl = round(realized_pnl, 2)
    file_hist_pnl = cap.get('hist_pnl', 0)
    if abs(calc_hist_pnl - file_hist_pnl) > 100:
        errors.append(f"hist_pnl 差异: 计算={calc_hist_pnl:,.2f} 文件={file_hist_pnl:,.2f} 差={calc_hist_pnl-file_hist_pnl:,.2f}")
    
    if errors:
        log("  ❌ 发现差异:")
        for e in errors:
            log(f"    {e}")
        
        # 自动修正
        log("  🔧 自动修正capital字段...")
        d['capital'] = {
            'initial': 1000000,
            'available': calc_avail,
            'market_value': round(market_value, 2),
            'total_assets': round(calc_total, 2),
            'hist_pnl': calc_hist_pnl,
            'hist_pnl': calc_hist_pnl,
            'total_pnl': round(calc_hist_pnl + pos_total_pnl, 2),
            'total': round(calc_total, 2),
            'total_pnl': round(calc_total - 1000000, 2),
            'total_market_value': round(market_value, 2),
            '_last_audit': datetime.now().isoformat(),
            '_audit_note': '自动复核修正'
        }
        with open(POSITION_FILE, 'w') as f:
            json.dump(d, f, ensure_ascii=False, indent=2)
        log("  ✅ 已修正并写回模拟持仓.json")
    else:
        log("  ✅ capital字段准确无误")
    
    # 5. 输出总结
    log("=== 复核结果 ===")
    log(f"  总资产: {calc_total:,.2f}")
    log(f"  累计盈亏: {calc_total-1000000:+,.2f} ({(calc_total-1000000)/1000000*100:+.2f}%)")
    log(f"  可用现金: {cash:,.2f}")
    log(f"  持仓市值: {market_value:,.2f}")
    log(f"  已实现盈亏: {realized_pnl:+,.2f}")
    log(f"  持仓累计浮动盈亏: {pos_total_pnl:+,.2f}")
    
    return len(errors) == 0

if __name__ == '__main__':
    ok = validate_and_fix()
    sys.exit(0 if ok else 1)
