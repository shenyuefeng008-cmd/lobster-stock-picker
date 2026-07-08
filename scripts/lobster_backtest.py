# -*- coding: utf-8 -*-
"""
🦞 龙虾三维度模拟回测引擎 v2.1
模拟区间：2026-05-06 ~ 2026-05-14（7个交易日）
规则：基于龙虾必读v2.1三维度体系
"""

import akshare as ak
import pandas as pd
import numpy as np
import json
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
TRADING = ROOT / 'trading'

# ============================================================
# 数据准备
# ============================================================

TRADE_DATES = ['20260506','20260507','20260508','20260511','20260512','20260513','20260514']

# 指数数据
indices_cfg = {
    '上证': ('sh000001', '000001'),
    '深成': ('sz399001', '399001'),
    '创业板': ('sz399006', '399006')
}
index_data = {}
for name, (sym, code) in indices_cfg.items():
    df = ak.stock_zh_index_daily(symbol=sym)
    df['date'] = df['date'].astype(str).str.replace('-','')
    df = df[df['date'].isin(TRADE_DATES)].copy().sort_values('date').reset_index(drop=True)
    df['pct_chg'] = df['close'].pct_change() * 100
    index_data[name] = df.set_index('date')

# 个股数据
STOCKS = {
    '英维克': '002837', '润泽科技': '300442', '蔚蓝锂芯': '002245',
    '杰华特': '688141', '科士达': '002518', '沪电股份': '002463',
    '中天科技': '600522', '杰瑞股份': '002353', '蒙娜丽莎': '002918',
    '大唐发电': '601991', '永鼎股份': '600105'
}
stock_data = {}
for name, code in STOCKS.items():
    prefix = 'sh' if code.startswith(('6','5')) else 'sz'
    df = ak.stock_zh_a_daily(symbol=(prefix + code), adjust='qfq')
    df['date'] = df['date'].astype(str).str.replace('-','')
    df = df[df['date'].isin(TRADE_DATES)].copy().sort_values('date').reset_index(drop=True)
    df['pct_chg'] = df['close'].pct_change() * 100
    df['ma5'] = df['close'].rolling(5, min_periods=1).mean()
    df['ma10'] = df['close'].rolling(10, min_periods=1).mean()
    df['ma20'] = df['close'].rolling(20, min_periods=1).mean()
    stock_data[name] = df.set_index('date')

# ============================================================
# 情绪数据（基于5/14记忆 + akshare涨停池估算）
# ============================================================

sentiment = {
    '20260506': {'updown': 1185, 'zt': 79,  'zbgc': 30, 'period': '冰点'},
    '20260507': {'updown': 2115, 'zt': 101, 'zbgc': 31, 'period': '修复期'},
    '20260508': {'updown': 2100, 'zt': 100, 'zbgc': 17, 'period': '修复期'},
    '20260511': {'updown': 2070, 'zt': 98,  'zbgc': 34, 'period': '修复期'},
    '20260512': {'updown': 2025, 'zt': 95,  'zbgc': 23, 'period': '修复期'},
    '20260513': {'updown': 2100, 'zt': 57,  'zbgc': 24, 'period': '修复期(缩量)'},
    '20260514': {'updown': 1010, 'zt': 55,  'zbgc': 48, 'period': '极度冰点'},
}

# 涨停个股数据（用于分析当日最强板块）
zhangting_stocks = {
    '20260506': ['大唐发电', '永鼎股份'],
    '20260507': ['科士达', '中天科技', '江苏国信'],
    '20260508': ['英维克', '科士达', '润泽科技'],
    '20260511': ['蒙娜丽莎', '蔚蓝锂芯', '杰华特'],
    '20260512': ['蒙娜丽莎', '英维克', '杰华特'],
    '20260513': ['沪电股份', '永鼎股份'],
    '20260514': ['大唐发电', '中国神华'],
}

def get_dimension(updown):
    if updown < 1500:
        return '1.0（冰点极值）'
    elif updown < 2500:
        return '1.0+3.0（修复期）'
    elif updown < 3500:
        return '2.0+1.0（高潮期）'
    else:
        return '辅助模式'

def get_position_limit(updown):
    """返回仓位上限（小数，如0.5表示50%）"""
    if updown < 1500:
        return 0.3  # 30%
    elif updown < 2000:
        return 0.4  # 40%
    elif updown < 2500:
        return 0.9  # 90%
    elif updown < 3500:
        return 0.7  # 70%
    else:
        return 0.2  # 20%

# ============================================================
# 模拟引擎
# ============================================================

initial_cash = 1_000_000
cash = initial_cash
portfolio = {}  # name -> {entry_date, entry_price, shares, hold_days, dimension, strategy}
trades = []
daily_records = []
equity_curve = [initial_cash]

def get_stock_valuation(portfolio_dict, date_str):
    """计算当前持仓市值"""
    total = 0
    for name, info in portfolio_dict.items():
        if name in stock_data and date_str in stock_data[name].index:
            price = stock_data[name].loc[date_str, 'close']
            total += price * info['shares']
    return total

def get_stock_price(name, date_str):
    if name in stock_data and date_str in stock_data[name].index:
        return stock_data[name].loc[date_str, 'close']
    return None

# ============================================================
# 主循环：逐日模拟
# ============================================================

for date_str in TRADE_DATES:
    date_idx = TRADE_DATES.index(date_str)
    sent = sentiment[date_str]
    dim_label = get_dimension(sent['updown'])
    pos_limit = get_position_limit(sent['updown'])
    up = index_data['上证'].loc[date_str, 'pct_chg'] if date_str in index_data['上证'].index else 0
    
    print(f"\n{'='*80}")
    print(f"📅 {date_str} | {sent['period']} | 涨跌{int(sent['updown']):,} | 涨停{sent['zt']}炸{sent['zbgc']} | 上证{up:+.1f}%")
    print(f"   维度: {dim_label} | 仓位上限: {int(pos_limit*100)}% | 持仓: {list(portfolio.keys())}")
    print(f"{'='*80}")
    
    # ---- Step 1: 更新持仓天数 & 检查卖出信号 ----
    sell_decisions = {}
    portfolio_copy = dict(portfolio)
    
    for stock_name, info in portfolio_copy.items():
        info['hold_days'] += 1  # 持仓天数+1（新买入当天为0，隔日为1）
        price = get_stock_price(stock_name, date_str)
        if price is None:
            continue
        
        pct_from_entry = (price / info['entry_price'] - 1) * 100
        stoploss_price = info['entry_price'] * 0.97
        dimension = info['dimension']
        
        sell = False
        reason = ''
        
        # === 1.0 隔日超短 ===
        if '1.0' in dimension and '3.0' not in dimension:
            if info['hold_days'] >= 1:  # T+1 隔日原则
                if pct_from_entry >= 3:
                    sell, reason = True, f'T+1止盈(+{pct_from_entry:.1f}%)'
                elif pct_from_entry > 0:
                    sell, reason = True, f'T+1小赚离场(+{pct_from_entry:.1f}%)'
                elif pct_from_entry <= -3:
                    sell, reason = f'止损(-{abs(pct_from_entry):.1f}%)'
                else:
                    sell, reason = f'T+1亏损持平({pct_from_entry:.1f}%)，离场观望'
                    
        # === 2.0 板块卡位 ===
        elif '2.0' in dimension:
            if info['hold_days'] >= 3:
                sell, reason = True, f'卡位满3日离场(持有{info["hold_days"]}天, {pct_from_entry:+.1f}%)'
            elif pct_from_entry <= -3:
                sell, reason = f'卡位止损(-{abs(pct_from_entry):.1f}%)'
            elif pct_from_entry >= 8:
                sell, reason = f'卡位目标达成(+{pct_from_entry:.1f}%)'
            # 板块退潮信号：如果板块内涨停数下降且个股走弱
            elif info['hold_days'] >= 2 and pct_from_entry < -1:
                sell, reason = f'卡位2日未走强({pct_from_entry:.1f}%)，止损'
                
        # === 3.0 趋势持股 ===
        elif '3.0' in dimension:
            ma10 = stock_data[stock_name].loc[date_str, 'ma10'] if date_str in stock_data[stock_name].index else 0
            # MA10 破位
            if price < ma10 * 0.97 and ma10 > 0:
                sell, reason = True, f'MA10破位({price:.2f} < {ma10:.2f})'
            elif pct_from_entry >= 8:
                sell, reason = f'趋势止盈(+{pct_from_entry:.1f}%)'
            elif pct_from_entry <= -7:
                sell, reason = f'趋势止损(-{abs(pct_from_entry):.1f}%)'
            elif info['hold_days'] >= 20:
                sell, reason = f'趋势持仓满20日'
        
        # 统一 -5% 硬止损
        if not sell and pct_from_entry <= -5:
            sell, reason = True, f'硬止损(-{abs(pct_from_entry):.1f}%)'
            
        if sell:
            sell_decisions[stock_name] = {'price': price, 'reason': reason, 'pct': pct_from_entry}
    
    # 执行卖出
    for stock_name, sd in sell_decisions.items():
        if stock_name not in portfolio:
            continue
        info = portfolio[stock_name]
        shares = info['shares']
        revenue = sd['price'] * shares
        pnl = (sd['price'] - info['entry_price']) * shares
        cash += revenue
        
        color = '🟢' if pnl >= 0 else '🔴'
        print(f"  {color} SELL {stock_name} | 价格:{sd['price']:.2f} | {shares}股 | 盈亏:{pnl:+,.0f} ({sd['pct']:+.1f}%) | 原因:{sd['reason']}")
        
        trades.append({
            'date': date_str, 'action': 'SELL', 'stock': stock_name,
            'price': round(sd['price'], 2), 'shares': shares,
            'revenue': round(revenue, 2),
            'pnl': round(pnl, 2), 'pnl_pct': round(sd['pct'], 2),
            'reason': sd['reason'], 'dimension': info['dimension']
        })
        del portfolio[stock_name]
    
    if not sell_decisions and portfolio:
        print(f"  ⏸️ 持仓未触发卖出条件，继续持有: {list(portfolio.keys())}")
    
    # ---- Step 2: 生成买入信号 ----
    buy_signals = []
    
    for stock_name in STOCKS:
        if stock_name in portfolio or stock_name not in stock_data:
            continue
        if date_str not in stock_data[stock_name].index:
            continue
        
        row = stock_data[stock_name].loc[date_str]
        price = row['close']
        pct = row['pct_chg']
        ma5 = row['ma5']
        ma10 = row['ma10']
        ma20 = row['ma20']
        
        # === 信号1: 1.0 跌幅后的分歧低吸（B/C型） ===
        # 条件：下跌2%-7%且接近MA5（日内超跌反弹预期）
        if -7 < pct < -1.5 and ma5 > 0:
            dist_to_ma5 = abs(price - ma5) / ma5 * 100
            if dist_to_ma5 < 3:  # 距MA5在3%以内
                buy_signals.append({
                    'stock': stock_name, 'type': '1.0-分歧低吸',
                    'priority': 1, 'price': price, 'pct': pct,
                    'detail': f'下跌{pct:.1f}%，距MA5{dist_to_ma5:.1f}%'
                })
        
        # === 信号2: 3.0 趋势多头低吸 ===
        # 条件：MA5>MA10>0，当日涨幅0~5%（健康上涨途中的回踩）
        if ma5 > ma10 > 0 and 0 < pct < 5:
            ma_dist = (price - ma10) / ma10 * 100
            if ma_dist > -2 and ma_dist < 4:  # 贴近MA10上方
                buy_signals.append({
                    'stock': stock_name, 'type': '3.0-趋势低吸',
                    'priority': 2, 'price': price, 'pct': pct,
                    'detail': f'MA多头(5:{ma5:.1f}>10:{ma10:.1f}), 距MA10{ma_dist:+.1f}%'
                })
    
    # === 信号特殊处理：基于记忆中的特定事件 ===
    # 5/11: 情绪修复日，关注昨日涨停的蔚蓝锂芯和杰华特是否给机会
    if date_str == '20260511':
        # 5/10 蔚蓝锂芯涨停，5/11如果给溢价但盘中回落，可低吸
        pass  # 由通用信号捕获
    
    # 5/13: 光大证券/券商异动，关注券商联动
    if date_str == '20260513':
        # 中天科技光模块概念，盘中如有异动可关注
        pass
    
    # === 信号排序和执行买入 ===
    buy_signals.sort(key=lambda x: (x['priority'], -x['pct']))
    
    # 仓位控制
    held_value = get_stock_valuation(portfolio, date_str)
    available = cash
    max_total_exposure = cash * pos_limit  # 总仓位上限
    max_single = cash * 0.35  # 单票上限35%
    current_exposure = held_value
    
    max_positions = 3 if sent['updown'] >= 1500 else 1
    
    for sig in buy_signals:
        if len(portfolio) >= max_positions:
            break
        if current_exposure + sig['price'] * 100 > max_total_exposure * 1.1:
            continue
        if sig['price'] * 100 > max_single:
            continue
            
        # 计算手数（100股/手）
        max_shares = int(min(max_single, max_total_exposure - current_exposure, available) / sig['price'] / 100) * 100
        if max_shares < 100:
            continue
            
        cost = sig['price'] * max_shares
        
        portfolio[sig['stock']] = {
            'entry_date': date_str,
            'entry_price': sig['price'],
            'shares': max_shares,
            'hold_days': 0,
            'dimension': sig['type'],
            'strategy': sig['detail']
        }
        cash -= cost
        current_exposure += cost
        
        print(f"  🟢 BUY {sig['stock']} | {max_shares}股 @ {sig['price']:.2f} = {cost:,.0f} | {sig['detail']}")
    
    # ---- Step 3: 收盘统计 ----
    stock_val = get_stock_valuation(portfolio, date_str)
    total_equity = cash + stock_val
    equity_curve.append(total_equity)
    
    if len(equity_curve) > 1:
        daily_ret = (total_equity / equity_curve[-2] - 1) * 100
    else:
        daily_ret = 0
    
    daily_records.append({
        'date': date_str,
        'equity': round(total_equity, 0),
        'cash': round(cash, 0),
        'stock_val': round(stock_val, 0),
        'daily_ret': round(daily_ret, 2),
        'sentiment': sent['period'],
        'updown': sent['updown']
    })
    
    print(f"\n  💰 资产: {total_equity:,.0f} | 现金:{cash:,.0f} | 持仓:{stock_val:,.0f} | 日收益:{daily_ret:+.1f}%")
    
    if portfolio:
        for name, info in portfolio.items():
            p = get_stock_price(name, date_str)
            if p:
                fp = (p / info['entry_price'] - 1) * 100
                print(f"     {name}: {info['shares']}股 @ {p:.2f} (成本{info['entry_price']:.2f}, {fp:+.1f}%, 持仓{info['hold_days']}日)")

# ============================================================
# 结果汇总
# ============================================================

final_equity = equity_curve[-1]
total_return = (final_equity / initial_cash - 1) * 100

# 统计卖出的胜率
sell_trades = [t for t in trades if t['action'] == 'SELL']
buy_trades = [t for t in trades if t['action'] == 'BUY']
winning = [t for t in sell_trades if t['pnl'] > 0]
losing = [t for t in sell_trades if t['pnl'] <= 0]

print(f"\n\n{'='*80}")
print(f"📊 【模拟回测最终报告】")
print(f"{'='*80}")
print(f"📅 测试期间: {TRADE_DATES[0]} ~ {TRADE_DATES[-1]} ({len(TRADE_DATES)}个交易日)")
print(f"💰 初始资金: {initial_cash:,.0f}")
print(f"💰 最终资产: {final_equity:,.0f}")
print(f"📈 总收益率: {total_return:+.2f}%")
print(f"📦 最大持仓: {max(r['stock_val'] for r in daily_records):,.0f}")
print(f"📉 最大回撤: {min(r['daily_ret'] for r in daily_records):+.1f}% (单日)")
print()
print(f"交易统计:")
print(f"  总买入次数: {len(buy_trades)}")
print(f"  总卖出次数: {len(sell_trades)}")
print(f"  胜率: {len(winning)/len(sell_trades)*100:.0f}%" if sell_trades else "  胜率: N/A (无卖出)")
if sell_trades:
    avg_win = np.mean([t['pnl_pct'] for t in winning]) if winning else 0
    avg_loss = np.mean([t['pnl_pct'] for t in losing]) if losing else 0
    win_rate = len(winning) / len(sell_trades) * 100
    profit_factor = abs(sum(t['pnl'] for t in winning) / sum(t['pnl'] for t in losing)) if losing and sum(t['pnl'] for t in losing) != 0 else float('inf')
    print(f"  平均盈利: {avg_win:+.2f}% | 平均亏损: {avg_loss:+.2f}%")
    print(f"  盈亏比: {profit_factor:.2f}x")
print()

# 未平仓
if portfolio:
    print(f"未平仓持仓:")
    for name, info in portfolio.items():
        p = get_stock_price(name, TRADE_DATES[-1])
        fp = (p / info['entry_price'] - 1) * 100 if p else 0
        val = p * info['shares'] if p else 0
        print(f"  {name}: {info['shares']}股, 成本{info['entry_price']:.2f}, 现价{p:.2f}, 浮盈{fp:+.1f}%, 市值{val:,.0f}")

# 每日收益表
print(f"\n{'='*80}")
print(f"📅 每日权益曲线")
print(f"{'='*80}")
print(f"{'日期':<12}{'总资产':>12}{'现金':>12}{'持仓':>12}{'日收益':>8}{'情绪':<12}{'涨跌家数':>10}")
print("-" * 78)
prev_eq = initial_cash
for r in daily_records:
    bar = '█' * max(1, int(abs(r['daily_ret']) / 2))
    print(f"{r['date']:<12}{r['equity']:>12,.0f}{r['cash']:>12,.0f}{r['stock_val']:>12,.0f}{r['daily_ret']:>+7.1f}% {r['sentiment']:<12}{r['updown']:>10,}")
    prev_eq = r['equity']

# 交易明细
print(f"\n{'='*80}")
print(f"📋 全量交易明细")
print(f"{'='*80}")
for i, t in enumerate(trades, 1):
    if t['action'] == 'BUY':
        print(f"  {i}. 🟢 {t['date']} BUY  {t['stock']:<8} {t['shares']:>5}股 @ {t['price']:>8.2f}")
    else:
        c = '🟢' if t['pnl'] >= 0 else '🔴'
        print(f"  {i}. {c} {t['date']} SELL {t['stock']:<8} {t['shares']:>5}股 @ {t['price']:>8.2f} → {t['pnl']:>+8,.0f} ({t['pnl_pct']:>+5.1f}%) | {t['reason']}")

# ============================================================
# 保存结果
# ============================================================
result = {
    'period': f"{TRADE_DATES[0]}至{TRADE_DATES[-1]}",
    'initial_cash': initial_cash,
    'final_equity': final_equity,
    'total_return_pct': round(total_return, 2),
    'total_buys': len(buy_trades),
    'total_sells': len(sell_trades),
    'winning_sells': len(winning),
    'losing_sells': len(losing),
    'daily_records': daily_records,
    'trades': trades,
    'open_positions': {k: v for k, v in portfolio.items()},
    'equity_curve': equity_curve
}

result_path = TRADING / 'sim_result.json'
with open(result_path, 'w', encoding='utf-8') as f:
    json.dump(result, f, ensure_ascii=False, indent=2)

print(f"\n✅ 结果已保存至 {result_path}")