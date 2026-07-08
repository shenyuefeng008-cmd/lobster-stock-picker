# -*- coding: utf-8 -*-
"""
🦞 龙虾系统蒙特卡洛进化模拟器 v2.0（修复版）
目标：2000次参数空间探索，找出最优参数组合

修复记录 v2.0:
- 持仓市值计算bug：cost存每股买入价，equity=shares*cost*(1+pct)
- 单日涨跌幅clip约束：±15%
- pnl_pct使用真实收益率：(proceeds-cost)/cost
"""

import numpy as np
import random
import json
from collections import defaultdict

np.random.seed(42)
random.seed(42)

# ============================================================
# 1. 历史交易日数据
# ============================================================
# (date, 上涨家数, 指数日涨跌幅%, 涨停数, 封板率, 板块主线)
HISTORICAL_DAYS = [
    ('20260506', 1185, -0.52, 79, 30, '电力'),
    ('20260507', 2115, +1.23, 101, 31, '元件/半导体'),
    ('20260508', 2100, +0.81, 100, 17, '半导体'),
    ('20260511', 2070, +0.92, 98,  34, '元件/半导体'),
    ('20260512', 2025, +1.15, 95,  23, '军工/AI'),
    ('20260513', 2100, +0.67, 57,  24, '混沌'),
    ('20260514', 1010, -1.84, 55,  48, '冰点恐慌'),
    ('20260519', 3356, +0.92, 90,  28, '高潮'),
    ('20260520', 1121, -2.04, 36,  40, '冰点'),
    ('20260521',  667, -2.35, 36,  69, '冰点恐慌'),
    ('20260525', 2058, +0.31, 72,  25, '混沌'),
    ('20260527', 1314, -0.52, 68,  37, '电力'),
    ('20260601', 1834, -0.31, 61,  45, '弱势'),
    ('20260602', 1512, -0.67, 44,  52, '冰点'),
    ('20260603', 1361, -0.64, 91,  35, '科技/电力'),
    ('20260604', 1294, -0.83, 91,  34, '弱市'),
    ('20260605', 2982, -0.74, 86,  32, '高潮'),
    ('20260608',  665, -1.70, 18,  55, '冰点恐慌'),
    ('20260609', 3216, +3.93, 120, 28, '高潮'),
    ('20260610', 1556, -2.70, 78,  38, '弱势'),
    ('20260611', 1351, -1.13, 69,  70, '半导体/有色'),
]

# 板块个股池：(名称, 代码, 昨日收盘价, 预期次日涨跌幅)
STOCK_POOL = {
    '电力': [
        ('华电能源', '600726', 3.21, +0.08),
        ('郴电国际', '600968', 8.72, +0.07),
        ('华能国际', '600011', 7.15, +0.09),
        ('大唐发电', '601991', 3.82, +0.06),
    ],
    '元件/半导体': [
        ('博敏电子', '603936', 25.16, -0.07),
        ('华天科技', '002185', 12.45, +0.04),
        ('生益科技', '600183', 22.30, +0.03),
        ('沪电股份', '002463', 38.50, +0.05),
    ],
    '军工/AI': [
        ('航发动力', '600893', 45.20, +0.06),
        ('中航沈飞', '600760', 52.30, +0.04),
        ('科大讯飞', '002230', 58.70, +0.07),
        ('寒武纪',   '688256',112.40, +0.10),
    ],
    '冰点恐慌': [
        ('天娱数科', '002354', 8.20, -0.10),
        ('达实智能', '002421', 5.79, -0.14),
        ('横店影视', '603103',18.50, -0.09),
        ('能科科技', '603859',42.30, -0.08),
    ],
    '高潮': [
        ('剑桥科技', '603083', 68.20, +0.08),
        ('中际旭创', '300308',158.30, +0.09),
        ('工业富联', '601138', 83.15, +0.06),
        ('新易盛',   '300502',128.40, +0.10),
    ],
    '科技/电力': [
        ('华工科技', '000988', 38.50, +0.05),
        ('杰瑞股份', '002353', 42.10, +0.06),
    ],
    '弱市': [
        ('稳健型标的', '000000', 10.00, +0.01),
    ],
    '半导体/有色': [
        ('和远气体', '002971', 28.40, +0.09),
        ('华特气体', '688268', 72.30, +0.06),
        ('翔鹭钨业', '002842', 12.80, +0.07),
    ],
    '混沌': [
        ('随机标的A', '000001', 15.00, 0.00),
    ],
}

# ============================================================
# 2. 参数空间
# ============================================================
class ParamSpace:
    def __init__(self):
        self.base = {
            'ice_thresh':       1500,
            'high_thresh':      3500,
            'melt_below':       1800,
            'pos_ice':          0.30,
            'pos_repair':       0.40,
            'pos_high':         0.70,
            'pos_over':         0.20,
            'pos_1d':           0.10,
            'pos_3d':           0.15,
            'stop_loss_1d':    -0.07,
            'stop_loss_3d':    -0.05,
            'tp_threshold':     0.05,
            'tp_retrace':       0.05,
            'yb_top_n':         6,
            'yb_score_min':    60,
            'yb_ice_score':    70,
            'cf_ice_enabled':   1,
            'bd_top_n':         4,
            'bd_score_min':     15,
            'bd_min_hold':      3,
            'td_min_score':    30,
            'td_min_hold':      3,
        }

    def sample(self, mutation_rate=0.30):
        p = {}
        for k, v in self.base.items():
            if isinstance(v, int):
                delta = max(1, int(v * mutation_rate))
                p[k] = max(1, v + random.randint(-delta, delta))
            elif isinstance(v, float):
                delta = abs(v * mutation_rate)
                p[k] = max(0.01, v + random.uniform(-delta, delta))
            else:
                p[k] = v
        return p

PARAM_SPACE = ParamSpace()

# ============================================================
# 3. 辅助函数
# ============================================================
def clip(val, lo, hi):
    return max(lo, min(hi, val))

def get_emotion_period(up_count, params):
    if up_count < params['ice_thresh']:
        return '冰点', params['pos_ice']
    elif up_count < params['melt_below']:
        return '冰点熔断', params['pos_ice']
    elif up_count < 2000:
        return '修复', params['pos_repair']
    elif up_count < params['high_thresh']:
        return '高潮', params['pos_high']
    else:
        return '极度高潮', params['pos_over']

# ============================================================
# 4. 模拟引擎
# ============================================================
def simulate_day(day_data, portfolio, params, capital):
    date_str, up_count, idx_pct, zt, zbgc, sector = day_data
    period, pos_limit = get_emotion_period(up_count, params)
    trades = []

    # ---- 选股 ----
    candidates = []
    if period in ('冰点', '冰点熔断'):
        pool = STOCK_POOL.get(sector, STOCK_POOL.get('混沌', []))[:2]
        for name, code, price, base_pct in pool:
            score = random.randint(params['yb_score_min'], 95)
            if score >= params['yb_ice_score']:
                actual = clip(base_pct + random.uniform(-0.04, 0.06), -0.12, 0.15)
                candidates.append({
                    'name': name, 'code': code, 'price': price,
                    'next_pct': actual, 'dim': '1.0-一进二', 'score': score
                })
        # 冰点分歧低吸
        if params['cf_ice_enabled']:
            pool2 = STOCK_POOL.get(sector, [])[2:4]
            for name, code, price, base_pct in pool2:
                if base_pct > -0.05:
                    actual = clip(base_pct + random.uniform(0.0, 0.06), -0.10, 0.12)
                    candidates.append({
                        'name': name, 'code': code,
                        'price': price * (1 + random.uniform(-0.02, 0.01)),
                        'next_pct': actual, 'dim': '1.0-分歧低吸', 'score': 65
                    })

    elif period in ('修复', '高潮'):
        pool = STOCK_POOL.get(sector, STOCK_POOL.get('混沌', []))
        for name, code, price, base_pct in pool:
            score = random.randint(params['bd_score_min'], 90)
            if score >= params['bd_score_min']:
                actual = clip(base_pct + random.uniform(0.0, 0.05), -0.08, 0.12)
                candidates.append({
                    'name': name, 'code': code, 'price': price,
                    'next_pct': actual, 'dim': '2.0-板块卡位', 'score': score
                })
        # 3.0趋势
        for sec in ['高潮', '电力']:
            for name, code, price, base_pct in STOCK_POOL.get(sec, [])[:1]:
                score = random.randint(params['td_min_score'], 85)
                if score >= params['td_min_score']:
                    actual = clip(base_pct + random.uniform(0.0, 0.04), -0.05, 0.10)
                    candidates.append({
                        'name': name, 'code': code, 'price': price,
                        'next_pct': actual, 'dim': '3.0-趋势低吸', 'score': score
                    })

    candidates.sort(key=lambda x: x['score'], reverse=True)
    top_n = params.get('yb_top_n', 6)
    candidates = candidates[:top_n]

    # ---- 买入 ----
    for c in candidates:
        dim_prefix = c['dim'].split('-')[0]
        single_pos = params['pos_1d'] if dim_prefix in ('1.0', '2.0') else params['pos_3d']
        pos_amt = capital * single_pos
        price = c['price']
        if pos_amt <= 0 or price <= 0 or not np.isfinite(pos_amt) or not np.isfinite(price):
            continue
        shares = int(pos_amt / price / 100) * 100
        if shares < 100:
            continue
        total_cost = shares * price
        if total_cost > capital:
            shares = int(capital / price / 100) * 100
            total_cost = shares * price
        if shares < 100:
            continue
        capital -= total_cost
        portfolio[c['name']] = {
            'code': c['code'], 'shares': shares,
            'cost': price,          # 每股买入价
            'total_cost': total_cost,  # 总投入
            'dim': c['dim'], 'hold_days': 0,
            'stop_loss': params['stop_loss_1d'] if dim_prefix in ('1.0', '2.0') else params['stop_loss_3d'],
            'tp_threshold': params['tp_threshold'],
            'tp_retrace': params['tp_retrace'],
            'next_pct': c['next_pct'],
        }

    # ---- 持仓卖出检查 ----
    to_sell = []
    for name, pos in list(portfolio.items()):
        pos['hold_days'] += 1
        actual_pct = clip(pos['next_pct'] + random.uniform(-0.02, 0.02), -0.15, 0.15)

        if actual_pct <= pos['stop_loss']:
            to_sell.append((name, '硬止损', actual_pct))
            continue
        if actual_pct > pos['tp_threshold']:
            retrace = actual_pct - pos['tp_threshold'] * 0.8
            if retrace >= pos['tp_retrace']:
                to_sell.append((name, '分时止盈', actual_pct))
                continue
        if pos['hold_days'] >= params.get('bd_min_hold', 3) and actual_pct > 0:
            to_sell.append((name, '超期不板', actual_pct))

    # ---- 执行卖出 ----
    daily_pnl = 0.0
    for name, reason, pct in to_sell:
        pos = portfolio.pop(name)
        proceeds = pos['shares'] * pos['cost'] * (1 + pct)
        pnl = proceeds - pos['total_cost']
        pnl_pct = pnl / pos['total_cost'] if pos['total_cost'] > 0 else 0
        daily_pnl += pnl
        capital += proceeds
        trades.append({
            'name': name, 'dim': pos['dim'],
            'reason': reason, 'pnl': pnl,
            'pnl_pct': pnl_pct, 'hold_days': pos['hold_days']
        })

    return capital, portfolio, trades, daily_pnl

def run_simulation(params, days, initial_capital=1_000_000):
    capital = initial_capital
    portfolio = {}
    all_trades = []
    equity = [float(initial_capital)]

    for day_data in days:
        capital, portfolio, trades, _ = simulate_day(day_data, portfolio, params, capital)
        all_trades.extend(trades)
        # 市值 = 股数 × 每股买入价 × (1 + 当日涨跌幅)
        holdings_value = 0.0
        for p in portfolio.values():
            pct = p.get('next_pct', 0)
            val = p['shares'] * p['cost'] * (1 + pct)
            holdings_value += max(0, val)
        equity.append(max(0.0, capital) + max(0.0, holdings_value))

    if not all_trades:
        return None

    pnls = [t['pnl_pct'] for t in all_trades]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p <= 0]

    # 最大回撤
    peak = equity[0]
    max_dd = 0.0
    for e in equity:
        if e > peak:
            peak = e
        dd = (peak - e) / peak if peak > 0 else 0
        if dd > max_dd:
            max_dd = dd

    total_return = (equity[-1] - initial_capital) / initial_capital
    sharpe = np.mean(pnls) / (np.std(pnls) + 1e-9) if len(pnls) > 1 else 0

    return {
        'total_return': total_return,
        'win_rate': len(wins) / len(pnls) if pnls else 0,
        'avg_win': np.mean(wins) if wins else 0,
        'avg_loss': np.mean(losses) if losses else 0,
        'max_drawdown': max_dd,
        'sharpe': sharpe,
        'num_trades': len(all_trades),
        'params': params,
        'trades': all_trades,
    }

# ============================================================
# 5. 主循环
# ============================================================
def run_evolution(n_iterations=2000):
    print(f"🦞 龙虾蒙特卡洛进化模拟器 v2.0（修复版）")
    print(f"   目标：{n_iterations}次参数空间探索")
    print(f"   数据：{len(HISTORICAL_DAYS)}个历史交易日 | 初始资金：100万")
    print("=" * 60)

    results = []
    best_return = -999
    best_result = None

    for i in range(n_iterations):
        params = PARAM_SPACE.sample(mutation_rate=0.30)
        res = run_simulation(params, HISTORICAL_DAYS)
        if res is None:
            continue
        results.append(res)
        if res['total_return'] > best_return:
            best_return = res['total_return']
            best_result = res
        if (i + 1) % 200 == 0:
            recent = results[-200:]
            med_ret = np.median([r['total_return'] for r in recent])
            med_wr  = np.median([r['win_rate']    for r in recent])
            print(f"   {i+1}/{n_iterations} | 中位收益 {med_ret:.1%} | 中位胜率 {med_wr:.1%} | 最优 {best_return:.1%}")

    print(f"\n{'='*60}")
    print(f"✅ 完成 {len(results)} 次有效模拟")

    returns  = [r['total_return']  for r in results]
    win_rates = [r['win_rate']      for r in results]
    max_dds   = [r['max_drawdown'] for r in results]

    print(f"\n📊 全局统计（2000次模拟）")
    print(f"   总收益率：平均 {np.mean(returns):.2%} | 中位数 {np.median(returns):.2%} | 标准差 {np.std(returns):.2%}")
    print(f"   胜率：平均 {np.mean(win_rates):.1%} | 中位数 {np.median(win_rates):.1%}")
    print(f"   最大回撤：平均 {np.mean(max_dds):.1%} | 中位数 {np.median(max_dds):.1%}")
    print(f"   正收益模拟：{sum(1 for r in returns if r > 0)}次 ({sum(1 for r in returns if r > 0)/len(results):.1%})")
    print(f"   负收益模拟：{sum(1 for r in returns if r < 0)}次 ({sum(1 for r in returns if r < 0)/len(results):.1%})")
    print(f"   持平模拟：{sum(1 for r in returns if abs(r) <= 0.001)}次")

    # ---- Top 10 ----
    results.sort(key=lambda x: x['total_return'], reverse=True)
    print(f"\n🏆 Top 10 最优参数（综合评分 = 收益×0.4 + 胜率×0.3 + 夏普×0.2 + 低回撤×0.1）")
    scored = []
    for r in results:
        score = (max(0, r['total_return']) * 40 +
                  r['win_rate'] * 30 +
                  max(0, r['sharpe']) * 20 +
                  (1 - r['max_drawdown']) * 10)
        scored.append((score, r))
    scored.sort(key=lambda x: x[0], reverse=True)

    print(f"{'名次':<4} {'综合分':>6} {'收益率':>8} {'胜率':>6} {'回撤':>6} {'夏普':>6} {'交易':>4}")
    print("-" * 55)
    for rank, (sc, r) in enumerate(scored[:10], 1):
        p = r['params']
        print(f"{rank:<4} {sc:>6.1f} {r['total_return']:>8.1%} {r['win_rate']:>6.1%} "
              f"{r['max_drawdown']:>6.1%} {r['sharpe']:>6.2f} {r['num_trades']:>4}")

    # ---- Bottom 5 ----
    print(f"\n💀 Worst 5 参数组合")
    for r in results[-5:]:
        p = r['params']
        wr = r['win_rate']
        ret = r['total_return']
        sl = p['stop_loss_1d']
        cf = 'Y' if p['cf_ice_enabled'] else 'N'
        print(f"  收益{ret:>7.1%} | 胜率{wr:>5.1%} | 止损{sl:>5.0%} | 冰点分歧:{cf}")

    # ---- 参数敏感性 ----
    print(f"\n📐 参数敏感性分析（Pearson相关系数 vs 收益率）")
    param_names = list(PARAM_SPACE.base.keys())
    correlations = {}
    for k in param_names:
        vals = [r['params'][k] for r in results]
        corr = np.corrcoef(returns, vals)[0, 1]
        if np.isfinite(corr):
            correlations[k] = corr
    sorted_corr = sorted(correlations.items(), key=lambda x: abs(x[1]), reverse=True)
    for k, corr in sorted_corr:
        direction = "→正" if corr > 0.05 else "→负" if corr < -0.05 else "  中性"
        strength = "★★★" if abs(corr) > 0.15 else "★★" if abs(corr) > 0.08 else "★"
        base_v = PARAM_SPACE.base[k]
        print(f"   {k:<20} r={corr:>+6.3f} {strength} {direction}  (基准{base_v})")

    # ---- 止损分析 ----
    print(f"\n🛑 止损阈值分析（最优止损区间）")
    sl_groups = defaultdict(list)
    for r in results:
        sl_bucket = f"{int(r['params']['stop_loss_1d']*100)}%"
        sl_groups[sl_bucket].append(r['total_return'])
    for k, rets in sorted(sl_groups.items(), key=lambda x: np.mean(x[1]), reverse=True):
        avg_r = np.mean(rets)
        pos_r = sum(1 for r in rets if r > 0) / len(rets)
        print(f"   -{k:>4} → 平均收益{avg_r:>7.2%} 正收益率{pos_r:>6.1%} (n={len(rets)})")

    # ---- 仓位分析 ----
    print(f"\n💰 仓位策略分析")
    pos_combos = defaultdict(list)
    for r in results:
        p = r['params']
        key = f"{int(p['pos_ice']*100)}/{int(p['pos_high']*100)}"
        pos_combos[key].append(r['total_return'])
    for k, rets in sorted(pos_combos.items(), key=lambda x: np.mean(x[1]), reverse=True)[:8]:
        avg_r = np.mean(rets)
        print(f"   冰点{int(k.split('/')[0]):>2}%/高潮{int(k.split('/')[1]):>2}% → 平均收益{avg_r:>7.2%} (n={len(rets)})")

    # ---- 冰点分歧低吸 ----
    print(f"\n❄️ 冰点分歧低吸开关")
    for enabled in (True, False):
        rets = [r['total_return'] for r in results if r['params']['cf_ice_enabled'] == enabled]
        wins = [r['win_rate']     for r in results if r['params']['cf_ice_enabled'] == enabled]
        label = '启用' if enabled else '禁用'
        avg_r = np.mean(rets) if rets else 0
        avg_w = np.mean(wins) if wins else 0
        pos_r = sum(1 for r in rets if r > 0) / len(rets) if rets else 0
        print(f"   {label} → 平均收益{avg_r:>7.2%} | 胜率{avg_w:>5.1%} | 正收益{pos_r:>5.1%} (n={len(rets)})")

    # ---- 综合建议 ----
    best = best_result
    p = best['params']
    print(f"\n🏆 最优参数建议（基于{n_iterations}次模拟）")
    print(f"   止损线：1.0/2.0 → {p['stop_loss_1d']:.0%} | 3.0 → {p['stop_loss_3d']:.0%}")
    print(f"   分时止盈：盈利>{p['tp_threshold']:.0%} 回落>{p['tp_retrace']:.0%}")
    print(f"   单仓：1.0/2.0 {p['pos_1d']:.0%} | 3.0 {p['pos_3d']:.0%}")
    print(f"   仓位：冰点{int(p['pos_ice']*100)}% | 修复{int(p['pos_repair']*100)}% | 高潮{int(p['pos_high']*100)}%")
    print(f"   一进二阈值：{p['yb_score_min']}（冰点期：{p['yb_ice_score']}）")
    print(f"   冰点分歧低吸：{'✅ 启用' if p['cf_ice_enabled'] else '❌ 禁用'}")
    print(f"   最优模拟指标：收益{best['total_return']:.2%} | 胜率{best['win_rate']:.1%} | 回撤{best['max_drawdown']:.1%}")

    # ---- 保存 ----
    output = {
        'n_iterations': n_iterations,
        'best_params': best['params'],
        'best_metrics': {
            'total_return': float(best['total_return']),
            'win_rate': float(best['win_rate']),
            'max_drawdown': float(best['max_drawdown']),
            'sharpe': float(best['sharpe']),
            'num_trades': int(best['num_trades']),
        },
        'global_stats': {
            'avg_return': float(np.mean(returns)),
            'median_return': float(np.median(returns)),
            'std_return': float(np.std(returns)),
            'avg_win_rate': float(np.mean(win_rates)),
            'positive_rate': sum(1 for r in returns if r > 0) / len(returns),
            'avg_max_dd': float(np.mean(max_dds)),
        },
        'param_correlations': {k: float(v) for k, v in correlations.items()},
        'top10': [
            {'score': sc, 'return': r['total_return'], 'win_rate': r['win_rate'],
             'max_dd': r['max_drawdown'], 'params': r['params']}
            for sc, r in scored[:10]
        ],
    }
    out_path = '/Users/yuefengshen/.qclaw/workspace-1gwpiwf3hr163jz5/trading/monte_carlo_evo_results.json'
    with open(out_path, 'w') as f:
        json.dump(output, f, indent=2, ensure_ascii=False, default=str)
    print(f"\n💾 结果已保存：{out_path}")

if __name__ == '__main__':
    run_evolution(2000)
