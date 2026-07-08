#!/usr/bin/env python3
"""
lobster_3p0_t0_script.py — 3.0趋势低吸 盘中T+0操作脚本

触发逻辑：
  T+0卖出：持仓≥1天后，当日从低位反弹≥2% + 浮盈≥3% → 卖出30%
  T+0回补：卖出后价格回落≥1.5% 或 触及当日低点 → 买回同等数量

用法：
  python3 lobster_3p0_t0_script.py --code 600487         # 单标的T+0巡检
  python3 lobster_3p0_t0_script.py --scan               # 扫描所有3.0持仓
  python3 lobster_3p0_t0_script.py --rebuy 600487 200   # 手动触发回补
  python3 lobster_3p0_t0_script.py --dry-run            # 不执行，只看信号
"""

import sys, os, json, datetime, argparse
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import urllib.request

WORKSPACE = '/Users/yuefengshen/.qclaw/workspace-1gwpiwf3hr163jz5'
CONFIG_PATH = os.path.join(WORKSPACE, 'lobster-config.json')
POSITIONS_PATH = os.path.join(WORKSPACE, 'trading/模拟持仓.json')
STATE_PATH = os.path.join(WORKSPACE, 'trading/3.0_t0_state.json')

# ──────────────────────────────────────────────
# 数据读取
# ──────────────────────────────────────────────

def load_config():
    with open(CONFIG_PATH) as f:
        return json.load(f)

def load_positions():
    with open(POSITIONS_PATH) as f:
        return json.load(f)

def load_t0_state():
    if os.path.exists(STATE_PATH):
        with open(STATE_PATH) as f:
            return json.load(f)
    return {'sold_today': {}, 't0_count': {}, 'last_t0_date': {}}

def save_t0_state(state):
    with open(STATE_PATH, 'w') as f:
        json.dump(state, f, ensure_ascii=False, indent=2)

def get_day_kline(code):
    """获取当日分时/K线数据"""
    # 格式转换
    market_map = {'sh': '1', 'sz': '0', 'bj': '0'}
    if code.startswith('sh'):
        mkt, c = '1', code[2:]
    elif code.startswith('sz'):
        mkt, c = '0', code[2:]
    elif code.startswith('bj'):
        mkt, c = '0', code[2:]
    else:
        return None

    # 腾讯实时行情
    url = f'https://qt.gtimg.cn/q=sz{code}' if code.startswith(('0','3')) else f'https://qt.gtimg.cn/q=sh{code}'
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        resp = urllib.request.urlopen(req, timeout=5)
        raw = resp.read().decode('gbk', errors='replace')
        fields = raw.split('~')
        if len(fields) < 10:
            return None
        current = float(fields[3])
        yesterday = float(fields[4])
        today_open = float(fields[5])
        day_high = float(fields[33])
        day_low = float(fields[34])
        volume = float(fields[6])  # 手

        return {
            'current': current,
            'yesterday_close': yesterday,
            'today_open': today_open,
            'day_high': day_high,
            'day_low': day_low,
            'change_pct': (current - yesterday) / yesterday * 100,
            'bounce_pct': (current - day_low) / day_low * 100 if day_low > 0 else 0,
        }
    except Exception as e:
        print(f'  ⚠️ 腾讯行情获取失败: {e}')
        return None

# ──────────────────────────────────────────────
# T+0 决策逻辑
# ──────────────────────────────────────────────

def check_t0_sell_signal(position, day_data, config, state):
    """检查是否触发T+0卖出信号"""
    code = position['code']
    today = datetime.date.today().isoformat()
    today_state = state.get('sold_today', {})

    # 安全检查：今日是否已做过T+0
    max_per_day = config['safety']['max_t0_per_day']
    if today_state.get(code, 0) >= max_per_day:
        return None, f"{code} 今日T+0次数已达上限({max_per_day})"

    # 浮盈检查
    profit_pct = position.get('total_pnl_pct', 0)
    min_profit = config['sell_trigger']['min_profit_pct']
    if profit_pct < min_profit:
        return None, f"浮盈{profit_pct:.2f}% < {min_profit}%门槛"

    # 从低位反弹检查
    bounce_pct = day_data['bounce_pct']
    min_bounce = config['sell_trigger']['min_bounce_from_low']
    if bounce_pct < min_bounce:
        return None, f"从低位反弹{bounce_pct:.2f}% < {min_bounce}%门槛"

    # 检查分时是否正在上涨（从低位反弹中）
    current = day_data['current']
    day_low = day_data['day_low']
    # 当前价离低点已有一定涨幅，但尚未反弹过头
    if bounce_pct > min_bounce * 2:
        return None, f"反弹{bounce_pct:.2f}%已过大，可等待"

    # 计算卖出数量（持仓的30%）
    pct_to_sell = config['sell_trigger']['pct_to_sell']
    shares = position['shares']
    min_retain = config['safety']['retain_min_shares']
    sell_shares = int((shares * pct_to_sell / 100) // 100) * 100
    sell_shares = max(100, sell_shares)
    if shares - sell_shares < min_retain:
        sell_shares = max(0, shares - min_retain)
    if sell_shares < 100:
        return None, f"卖出后剩余{shares-sell_shares}股不足{min_retain}股"

    return {
        'action': 'SELL',
        'code': code,
        'name': position['name'],
        'sell_price': current,
        'sell_shares': sell_shares,
        'sell_pct': round(sell_shares / shares * 100, 1),
        'current_profit_pct': round(profit_pct, 2),
        'bounce_pct': round(bounce_pct, 2),
        'day_low': day_low,
    }, None

def check_t0_rebuy_signal(sold_info, day_data, config):
    """检查是否触发T+0回补信号"""
    if not sold_info:
        return None, "无卖出记录"

    current = day_data['current']
    sell_price = sold_info['sell_price']

    # 回补触发1：从卖出点回落≥1.5%
    pullback_pct = (sell_price - current) / sell_price * 100
    min_pullback = config['rebuy_trigger']['pullback_pct']

    # 回补触发2：触及当日低点
    day_low = day_data['day_low']

    if pullback_pct >= min_pullback:
        return {
            'action': 'REBUY',
            'code': sold_info['code'],
            'name': sold_info['name'],
            'rebuy_price': current,
            'rebuy_shares': sold_info['sell_shares'],
            'pullback_pct': round(pullback_pct, 2),
            'sell_price': sell_price,
            'day_low': day_low,
            'gain_pct': round((sell_price - current) / sell_price * 100, 2),
        }, None

    if config['rebuy_trigger']['or_touch_day_low']:
        if abs(current - day_low) / day_low < 0.003:  # 距低点<0.3%
            return {
                'action': 'REBUY',
                'code': sold_info['code'],
                'name': sold_info['name'],
                'rebuy_price': current,
                'rebuy_shares': sold_info['sell_shares'],
                'pullback_pct': round(pullback_pct, 2),
                'trigger': 'touch_day_low',
                'day_low': day_low,
            }, None

    return None, "未触发回补条件"

# ──────────────────────────────────────────────
# 执行层（复用simulated_trading.py的函数）
# ──────────────────────────────────────────────

def do_sell_partial(code, pct_to_sell, sell_price, reason):
    """调用simulated_trading.py执行部分卖出"""
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    try:
        from simulated_trading import sell_partial
        result = sell_partial(code, pct_to_sell=pct_to_sell, sell_price=sell_price,
                              reason=reason, sell_type='3.0_T+0卖出')
        return result
    except (ImportError, TypeError) as e:
        # 直接导入失败，手动构造
        return f"[DRY-RUN] 应调用 sell_partial({code}, pct_to_sell={pct_to_sell}, sell_price={sell_price}, reason={reason})"

def do_rebuy(code, shares, price):
    """执行T+0回补买入（视为普通买入）"""
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    try:
        from simulated_trading import buy
        # buy() 签名: buy(code, name, price, reason, dimension, ...)
        result = buy(code=code, name=name, price=price,
                    reason=f'3.0 T+0回补 {shares}股@{price}',
                    dimension='3.0-趋势低吸(T+0回补)')
        return result
    except (ImportError, TypeError) as e:
        return f"[DRY-RUN] 应调用 buy({code}, {name}, {price}, ...)"

# ──────────────────────────────────────────────
# 主流程
# ──────────────────────────────────────────────

def scan_all_3p0_positions(dry_run=True, verbose=True):
    """扫描所有3.0持仓，返回可做T+0的标的"""
    config = load_config()
    data = load_positions()
    state = load_t0_state()
    t0_cfg = config.get('3.0_t0_rules', {})
    today = datetime.date.today().isoformat()

    if not t0_cfg.get('enabled', False):
        if verbose:
            print('⚠️ 3.0 T+0功能未启用（config中disabled）')
        return

    signals = []
    for pos in data.get('positions', []):
        dim = pos.get('dimension', '')
        if '3.0' not in dim:
            continue

        code = pos['code']
        name = pos.get('name', code)
        shares = pos['shares']

        # T+1检查
        buy_date = datetime.date.fromisoformat(pos.get('buy_date', today))
        hold_days = (datetime.date.today() - buy_date).days
        min_hold = t0_cfg.get('min_hold_days_for_t0', 1)
        if hold_days < min_hold:
            if verbose:
                print(f'  ⏳ {name}({code}) 持有{hold_days}天 < {min_hold}天(T+1)，跳过')
            continue

        # 获取当日行情
        day_data = get_day_kline(code)
        if not day_data:
            if verbose:
                print(f'  ⚠️ {name}({code}) 行情获取失败')
            continue

        # 检查卖出信号
        sig, msg = check_t0_sell_signal(pos, day_data, t0_cfg, state)
        if verbose:
            print(f'  [{name}({code})] 浮盈{pos.get("total_pnl_pct",0):.2f}% | '
                  f'今日反弹{day_data["bounce_pct"]:.2f}% | {msg}')

        if sig:
            signals.append(('SELL', sig, day_data))

        # 检查回补信号
        sold = state.get('pending_rebuy', {}).get(code)
        if sold:
            sig2, msg2 = check_t0_rebuy_signal(sold, day_data, t0_cfg)
            if sig2 and verbose:
                print(f'  🔁 回补信号: {name}({code}) 从{sold["sell_price"]}回落{sig2["pullback_pct"]}% → 建议{sig2["rebuy_shares"]}股@{sig2["rebuy_price"]}')
            if sig2:
                signals.append(('REBUY', sig2, day_data))

    return signals

def execute_t0_operation(signals, dry_run=True):
    """执行T+0操作"""
    state = load_t0_state()
    today = datetime.date.today().isoformat()

    # 初始化当日计数
    if 'sold_today' not in state:
        state['sold_today'] = {}
    if state.get('_last_date') != today:
        state = {'sold_today': {}, 't0_count': state.get('t0_count', {}),
                 'last_t0_date': state.get('last_t0_date', {}), '_last_date': today}

    for action, sig, day_data in signals:
        code = sig['code']
        name = sig['name']

        if action == 'SELL':
            pct = sig['sell_pct']
            price = sig['sell_price']
            shares = sig['sell_shares']

            print(f'📤 3.0 T+0 SELL: {name}({code}) 卖出{shares}股({pct}%)@{price}')
            if not dry_run:
                # 执行卖出
                result = do_sell_partial(code, pct, price, f'3.0 T+0卖出 {shares}股')
                print(f'  → {result}')
                # 记录pending rebuy
                if 'pending_rebuy' not in state:
                    state['pending_rebuy'] = {}
                state['pending_rebuy'][code] = {
                    'sell_price': price,
                    'sell_shares': shares,
                    'sell_time': datetime.datetime.now().strftime('%H:%M:%S'),
                    'sell_date': today,
                }
                state['sold_today'][code] = state['sold_today'].get(code, 0) + 1
                # 更新计数
                state['t0_count'][code] = state['t0_count'].get(code, 0) + 1
                state['last_t0_date'][code] = today

        elif action == 'REBUY':
            price = sig['rebuy_price']
            shares = sig['rebuy_shares']
            print(f'📥 3.0 T+0 REBUY: {name}({code}) 回补{shares}股@{price}')
            if not dry_run:
                result = do_rebuy(code, shares, price)
                print(f'  → {result}')
                # 清除pending
                if 'pending_rebuy' in state and code in state['pending_rebuy']:
                    del state['pending_rebuy'][code]

        save_t0_state(state)

    if not signals:
        print('✅ 今日无T+0信号（继续持有观望）')

    return signals

def main():
    parser = argparse.ArgumentParser(description='3.0趋势低吸 盘中T+0脚本')
    parser.add_argument('--code', help='指定股票代码')
    parser.add_argument('--scan', action='store_true', help='扫描所有3.0持仓')
    parser.add_argument('--rebuy', nargs=3, metavar=('CODE', 'SHARES', 'PRICE'),
                        help='手动触发回补: 代码 股数 价格')
    parser.add_argument('--dry-run', dest='dry_run', action='store_true', default=True,
                        help='只查看信号，不执行（默认）')
    parser.add_argument('--execute', action='store_true', help='实际执行（需显式指定）')
    args = parser.parse_args()

    dry_run = not args.execute

    if args.rebuy:
        code, shares, price = args.rebuy
        sig = {
            'action': 'REBUY',
            'code': code,
            'name': '手动指定',
            'rebuy_price': float(price),
            'rebuy_shares': int(shares),
            'sell_shares': int(shares),
        }
        day_data = get_day_kline(code)
        execute_t0_operation([('REBUY', sig, day_data or {})], dry_run=dry_run)
        return

    if args.scan or args.code:
        if args.code:
            positions = load_positions()
            pos = next((p for p in positions.get('positions', []) if p['code'] == args.code), None)
            if not pos:
                print(f'⚠️ 未找到持仓: {args.code}')
                return
            positions['positions'] = [pos]
            data = load_positions()  # 保持原状
        else:
            data = load_positions()

        signals = scan_all_3p0_positions(dry_run=True, verbose=True)
        if signals and (args.execute or input('是否执行以上信号? [y/具体标的]: ').strip().lower() == 'y'):
            execute_t0_operation(signals, dry_run=dry_run)
    else:
        print(__doc__)
        print('\n示例用法:')
        print('  python3 lobster_3p0_t0_script.py --scan --dry-run    # 扫描所有3.0持仓(不执行)')
        print('  python3 lobster_3p0_t0_script.py --scan --execute   # 扫描+执行')
        print('  python3 lobster_3p0_t0_script.py --code 600487      # 只看亨通光电')

if __name__ == '__main__':
    main()
