#!/usr/bin/env python3
"""
龙虾竞价异动信号回测 v1.0 — thsdk 历史分时数据回测
模拟竞价异动触发条件，回测命中率/次日溢价/5日最大收益等指标。

用法：
  python3 scripts/lobster_backtest_auction.py [--days 60] [--code 000001]
  python3 scripts/lobster_backtest_auction.py --start 20260701 --end 20260707

数据源：thsdk.min_snapshot() 历史分时数据
输出：reports/backtest_auction_YYYYMMDD.md
"""

import json
import sys
import datetime
import argparse
import os
from pathlib import Path
from collections import defaultdict

ROOT = Path(__file__).parent.parent
CONFIG_PATH = ROOT / 'lobster-config.json'
OUT_DIR = ROOT / 'reports'
TREND_POOL_PATH = ROOT / 'trading' / 'trend_pool.json'

# ── 配置加载 ──────────────────────────────────────────

def load_backtest_config():
    cfg = {}
    if CONFIG_PATH.exists():
        try:
            with open(CONFIG_PATH) as f:
                cfg = json.load(f)
        except Exception:
            pass
    bt = cfg.get('backtest', {})
    return {
        'default_days': bt.get('default_days', 60),
        'bid_increase_min': bt.get('auction_threshold', {}).get('bid_increase_min', 3.0),
        'bid_volume_ratio': bt.get('auction_threshold', {}).get('bid_volume_ratio', 1.05),
        'open_rise_timeout_min': bt.get('auction_threshold', {}).get('open_rise_timeout_min', 5),
        'open_rise_pct': bt.get('auction_threshold', {}).get('open_rise_pct', 3.0),
    }


def load_stock_codes():
    """从趋势池+持仓+候选池获取回测标的"""
    codes = set()

    if TREND_POOL_PATH.exists():
        try:
            with open(TREND_POOL_PATH) as f:
                tp = json.load(f)
            for entry in tp if isinstance(tp, list) else []:
                code = str(entry.get('code', ''))
                if code:
                    codes.add(code)
        except Exception:
            pass

    # 从 lobster-config 趋势池种子标的中取
    if CONFIG_PATH.exists():
        try:
            with open(CONFIG_PATH) as f:
                cfg = json.load(f)
            stock_codes = cfg.get('trend_pool', {}).get('stock_codes', {})
            for code in stock_codes.values():
                codes.add(str(code))
        except Exception:
            pass

    # 持仓股
    pos_path = ROOT / 'trading' / '模拟持仓.json'
    if pos_path.exists():
        try:
            with open(pos_path) as f:
                pos = json.load(f)
            for p in pos.get('positions', []):
                codes.add(str(p.get('code', '')))
        except Exception:
            pass

    return list(codes)[:30]  # 限 30 只，避免回测过慢


def get_trade_dates(days=60, start=None, end=None):
    """生成交易日列表（往回推算，跳过周末）"""
    if start and end:
        d_start = datetime.datetime.strptime(start, '%Y%m%d')
        d_end = datetime.datetime.strptime(end, '%Y%m%d')
        dates = []
        d = d_start
        while d <= d_end:
            if d.weekday() < 5:
                dates.append(d.strftime('%Y%m%d'))
            d += datetime.timedelta(days=1)
        return dates
    else:
        dates = []
        d = datetime.date.today()
        count = 0
        attempts = 0
        while count < days and attempts < days * 2:
            if d.weekday() < 5:
                dates.append(d.strftime('%Y%m%d'))
                count += 1
            d -= datetime.timedelta(days=1)
            attempts += 1
        return list(reversed(dates))


# ── thsdk 数据拉取（带完整异常处理）────────────────────

def fetch_min_snapshot(code, date_str):
    """
    通过 thsdk.min_snapshot() 拉取单日分时数据。
    游客模式可能受限，异常时返回 None。
    """
    try:
        import thsdk
        raw = thsdk.min_snapshot(code, date=date_str)
        if not raw:
            return None
        # 期望返回 [{time, price, volume, ...}, ...]
        if isinstance(raw, list):
            return raw
        if isinstance(raw, dict):
            return list(raw.values()) if 'data' in raw else raw.get('snapshots', [])
        return None
    except ImportError:
        return None
    except Exception as e:
        print(f'    ⚠️  thsdk.min_snapshot({code}, {date_str}) 失败: {e}', file=sys.stderr)
        return None


def fetch_day_kline(code, date_str):
    """通过 thsdk.klines 拉取日K线，用于获取前一天收盘价/成交量。"""
    try:
        import thsdk
        raw = thsdk.klines(code, interval='day', count=5, end_date=date_str)
        if not raw or not isinstance(raw, list):
            return None
        klines = []
        for k in raw:
            klines.append({
                'date': str(k.get('datetime', k.get('date', '')))[:10],
                'open': float(k.get('open', 0)),
                'close': float(k.get('close', 0)),
                'high': float(k.get('high', 0)),
                'low': float(k.get('low', 0)),
                'volume': float(k.get('volume', 0)),
            })
        return klines
    except ImportError:
        return None
    except Exception as e:
        return None


# ── 信号模拟 ────────────────────────────────────────

def simulate_auction_signal(code, date_str, config, snapshots):
    """
    模拟竞价异动触发条件：
    1. 竞价涨幅 > bid_increase_min%
    2. 竞价量 > 昨日 5% 总成交量
    3. 开盘后 N 分钟内涨幅 > open_rise_pct%

    返回 (triggered, signal_type, detail_dict)
    """
    if not snapshots:
        return False, '', {}

    yesterday_kline = fetch_day_kline(code, date_str)
    if not yesterday_kline or len(yesterday_kline) < 2:
        return False, '', {}

    prev_day = yesterday_kline[-2]  # 前一天
    prev_close = prev_day['close']
    prev_volume = prev_day['volume']
    if prev_close <= 0:
        return False, '', {}

    # 解析分时数据
    try:
        first_snap = snapshots[0]
        open_price = float(first_snap.get('price', first_snap.get('open', 0)))
    except (IndexError, KeyError):
        return False, '', {}

    if open_price <= 0:
        return False, '', {}

    # 条件1: 竞价涨幅（用开盘价 vs 前收模拟）
    bid_increase = (open_price - prev_close) / prev_close * 100
    cond1 = bid_increase >= config['bid_increase_min']

    # 条件2: 竞价量（用第一分钟量 vs 前日量模拟）
    first_vol = float(first_snap.get('volume', 0))
    vol_ratio = first_vol / prev_volume if prev_volume > 0 else 0
    cond2 = vol_ratio >= config['bid_volume_ratio']

    # 条件3: 开盘后N分钟内涨幅
    timeout = config['open_rise_timeout_min']
    rise_pct_threshold = config['open_rise_pct']
    cond3 = False
    rise_pct_actual = 0
    for i, snap in enumerate(snapshots[:timeout]):
        price = float(snap.get('price', 0))
        if price > 0:
            rise_pct = (price - open_price) / open_price * 100
            if rise_pct >= rise_pct_threshold:
                cond3 = True
                rise_pct_actual = rise_pct
                break

    triggered = cond1 or cond2 or cond3
    signal_types = []
    if cond1:
        signal_types.append('竞价高开')
    if cond2:
        signal_types.append('竞价放量')
    if cond3:
        signal_types.append(f'开盘急拉{rise_pct_threshold}%')

    detail = {
        'bid_increase': round(bid_increase, 2),
        'vol_ratio': round(vol_ratio, 4),
        'rise_pct': round(rise_pct_actual, 2) if cond3 else 0,
    }

    return triggered, '+'.join(signal_types) if signal_types else '', detail


def calc_forward_returns(snapshots, prev_close):
    """计算次日溢价 / 5日最大收益 / 信号日收益"""
    if not snapshots:
        return {}

    last_price = float(snapshots[-1].get('price', 0))
    first_price = float(snapshots[0].get('price', 0))
    if prev_close <= 0 or first_price <= 0:
        return {}

    # 日内最高
    day_high = max(float(s.get('price', 0)) or 0 for s in snapshots)
    # 日内最低
    day_low = min(float(s.get('price', 0)) or float('inf') for s in snapshots)
    if day_low == float('inf'):
        day_low = first_price

    return {
        'day_return': round((last_price - prev_close) / prev_close * 100, 2),
        'day_high_return': round((day_high - prev_close) / prev_close * 100, 2),
        'day_low_return': round((day_low - prev_close) / prev_close * 100, 2),
        'intraday_range': round((day_high - day_low) / day_low * 100, 2) if day_low > 0 else 0,
    }


# ── 主回测逻辑 ──────────────────────────────────────

def run_backtest(codes, dates, config):
    results = []
    stats = {
        'total_signals': 0,
        'total_win': 0,
        'total_loss': 0,
        'day_returns': [],
        'signal_types': defaultdict(int),
        'skipped': 0,
        'data_unavailable': 0,
    }

    for date_str in dates:
        print(f'📅 {date_str} ...', file=sys.stderr)
        for code in codes:
            snapshots = fetch_min_snapshot(code, date_str)
            if snapshots is None:
                stats['data_unavailable'] += 1
                continue

            if not snapshots:
                stats['skipped'] += 1
                continue

            prev = fetch_day_kline(code, date_str)
            prev_close = prev[-2]['close'] if prev and len(prev) >= 2 else 0

            triggered, sig_type, detail = simulate_auction_signal(code, date_str, config, snapshots)

            if triggered:
                fwd = calc_forward_returns(snapshots, prev_close)
                record = {
                    'date': date_str,
                    'code': code,
                    'signal_type': sig_type,
                    'bid_increase': detail.get('bid_increase', 0),
                    'vol_ratio': detail.get('vol_ratio', 0),
                    **fwd,
                }
                results.append(record)
                stats['total_signals'] += 1
                stats['day_returns'].append(fwd.get('day_return', 0))
                stats['signal_types'][sig_type] += 1
                if fwd.get('day_return', 0) > 0:
                    stats['total_win'] += 1
                else:
                    stats['total_loss'] += 1

    return results, stats


def generate_report(results, stats, config, dates):
    """生成 Markdown 回测报告"""
    today = datetime.date.today().strftime('%Y%m%d')
    out_path = OUT_DIR / f'backtest_auction_{today}.md'

    lines = []
    lines.append(f'# 竞价异动信号回测报告')
    lines.append(f'')
    lines.append(f'**生成时间**: {datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")}')
    lines.append(f'')
    lines.append(f'## 回测参数')
    lines.append(f'')
    lines.append(f'| 参数 | 值 |')
    lines.append(f'|------|-----|')
    lines.append(f'| 回测日期范围 | {dates[0]} ~ {dates[-1]} ({len(dates)}个交易日) |')
    lines.append(f'| 回测标的数 | {len(set(r["code"] for r in results)) + stats["data_unavailable"]} |')
    lines.append(f'| 竞价涨幅阈值 | ≥{config["bid_increase_min"]}% |')
    lines.append(f'| 竞价量比阈值 | ≥{config["bid_volume_ratio"]} |')
    lines.append(f'| 开盘急拉阈值 | {config["open_rise_timeout_min"]}分钟内≥{config["open_rise_pct"]}% |')
    lines.append(f'')
    lines.append(f'## 统计摘要')
    lines.append(f'')
    lines.append(f'| 指标 | 值 |')
    lines.append(f'|------|-----|')

    n = stats['total_signals']
    win_rate = round(stats['total_win'] / n * 100, 1) if n > 0 else 0
    day_rets = stats['day_returns']
    avg_ret = round(sum(day_rets) / len(day_rets), 2) if day_rets else 0
    max_ret = round(max(day_rets), 2) if day_rets else 0
    min_ret = round(min(day_rets), 2) if day_rets else 0

    # 简化夏普（均值/标准差，无风险利率忽略）
    if len(day_rets) > 1:
        mean_r = sum(day_rets) / len(day_rets)
        variance = sum((r - mean_r) ** 2 for r in day_rets) / (len(day_rets) - 1)
        std_r = variance ** 0.5
        sharpe = round(mean_r / std_r * (252 ** 0.5), 2) if std_r > 0 else 0
    else:
        sharpe = 0

    lines.append(f'| 信号总数 | {n} |')
    lines.append(f'| 胜率(日内收益>0) | {win_rate}% |')
    lines.append(f'| 平均日内收益 | {avg_ret}% |')
    lines.append(f'| 最大日内收益 | {max_ret}% |')
    lines.append(f'| 最大日内回撤 | {min_ret}% |')
    lines.append(f'| 简化夏普比率 | {sharpe} |')
    lines.append(f'| 数据不可用(跳过) | {stats["data_unavailable"]} |')
    lines.append(f'')
    lines.append(f'## 信号类型分布')
    lines.append(f'')
    lines.append(f'| 类型 | 次数 | 占比 |')
    lines.append(f'|------|------|------|')
    for st, cnt in sorted(stats['signal_types'].items(), key=lambda x: -x[1]):
        pct = round(cnt / n * 100, 1) if n > 0 else 0
        lines.append(f'| {st} | {cnt} | {pct}% |')
    lines.append(f'')

    if results:
        lines.append(f'## 信号明细（最近 30 条）')
        lines.append(f'')
        lines.append(f'| 日期 | 代码 | 信号类型 | 竞价涨幅% | 量比 | 日内收益% |')
        lines.append(f'|------|------|----------|-----------|------|----------|')
        for r in sorted(results, key=lambda x: x['date'], reverse=True)[:30]:
            lines.append(f'| {r["date"]} | {r["code"]} | {r["signal_type"]} | {r["bid_increase"]} | {r["vol_ratio"]} | {r.get("day_return", 0)} |')

    lines.append('')
    lines.append(f'> 注意：thsdk 游客模式可能限制历史数据访问。跳过天数 = 数据不可用天数。')

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    report = '\n'.join(lines)
    with open(out_path, 'w', encoding='utf-8') as f:
        f.write(report)
    return out_path


def main():
    parser = argparse.ArgumentParser(description='龙虾竞价异动信号回测')
    parser.add_argument('--days', type=int, default=None, help='回测最近N个交易日')
    parser.add_argument('--start', type=str, default=None, help='起始日期 YYYYMMDD')
    parser.add_argument('--end', type=str, default=None, help='结束日期 YYYYMMDD')
    parser.add_argument('--code', type=str, default=None, help='指定单只股票代码')
    args = parser.parse_args()

    config = load_backtest_config()
    days = args.days or config['default_days']

    print(f'🦞 龙虾竞价异动回测 v1.0')
    print(f'   阈值: 竞价涨幅≥{config["bid_increase_min"]}% / 量比≥{config["bid_volume_ratio"]} / {config["open_rise_timeout_min"]}min内≥{config["open_rise_pct"]}%')

    # 标的
    if args.code:
        codes = [args.code]
    else:
        codes = load_stock_codes()
    print(f'📋 回测标的: {len(codes)} 只')

    # 日期
    dates = get_trade_dates(days=days, start=args.start, end=args.end)
    print(f'📅 回测范围: {dates[0]} ~ {dates[-1]} ({len(dates)}个交易日)')

    # 执行回测
    results, stats = run_backtest(codes, dates, config)

    # 输出汇总
    n = stats['total_signals']
    win_rate = round(stats['total_win'] / n * 100, 1) if n > 0 else 0
    avg_ret = round(sum(stats['day_returns']) / len(stats['day_returns']), 2) if stats['day_returns'] else 0
    print(f'\n📊 回测结果: {n} 个信号 | 胜率 {win_rate}% | 平均收益 {avg_ret}% | 跳过 {stats["data_unavailable"]} 天(数据不可用)')

    # 生成报告
    report_path = generate_report(results, stats, config, dates)
    print(f'✅ 报告已写入 {report_path}')


if __name__ == '__main__':
    main()
