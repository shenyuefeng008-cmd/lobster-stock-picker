#!/usr/bin/env python3
"""
龙虾回测执行器 v1.0 — 整合竞价异动回测 + 分钟K线回测
一键运行全部回测，汇总输出报告。

用法：
  python3 scripts/lobster_backtest_runner.py --days 60
  python3 scripts/lobster_backtest_runner.py --days 30 --code 000001
  python3 scripts/lobster_backtest_runner.py --auction-only
  python3 scripts/lobster_backtest_runner.py --minute-only

输出：reports/backtest_summary_YYYYMMDD.md
"""

import json
import sys
import datetime
import argparse
import subprocess
import os
from pathlib import Path

ROOT = Path(__file__).parent.parent
CONFIG_PATH = ROOT / 'lobster-config.json'
OUT_DIR = ROOT / 'reports'
SCRIPT_DIR = Path(__file__).parent


def load_config():
    cfg = {}
    if CONFIG_PATH.exists():
        try:
            with open(CONFIG_PATH) as f:
                cfg = json.load(f)
        except Exception:
            pass
    return cfg.get('backtest', {})


def run_auction_backtest(days, code=None):
    """调用竞价异动回测子程序，返回 (success, output) 元组。"""
    print('▶️  运行竞价异动回测...')
    cmd = [sys.executable, str(SCRIPT_DIR / 'lobster_backtest_auction.py'), '--days', str(days)]
    if code:
        cmd += ['--code', code]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=3600, cwd=str(ROOT))
        ok = r.returncode == 0
        if not ok:
            print(f'  ⚠️  竞价回测异常退出 (code={r.returncode})')
            print(f'  stderr: {r.stderr[-300:]}')
        return ok, r.stdout, r.stderr
    except subprocess.TimeoutExpired:
        print('  ⚠️  竞价回测超时 (3600s)')
        return False, '', 'TIMEOUT'
    except Exception as e:
        print(f'  ⚠️  竞价回测执行失败: {e}')
        return False, '', str(e)


def run_minute_backtest(days, code=None):
    """调用分钟K线回测子程序，返回 (success, output)。"""
    print('▶️  运行分钟K线回测...')
    cmd = [sys.executable, str(SCRIPT_DIR / 'lobster_backtest_minute.py'), '--days', str(days)]
    if code:
        cmd += ['--code', code]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=3600, cwd=str(ROOT))
        ok = r.returncode == 0
        if not ok:
            print(f'  ⚠️  分钟K线回测异常退出 (code={r.returncode})')
        return ok, r.stdout, r.stderr
    except subprocess.TimeoutExpired:
        print('  ⚠️  分钟K线回测超时 (3600s)')
        return False, '', 'TIMEOUT'
    except Exception as e:
        print(f'  ⚠️  分钟K线回测执行失败: {e}')
        return False, '', str(e)


def parse_auction_summary(stdout):
    """从竞价回测 stdout 提取统计行。"""
    for line in stdout.split('\n'):
        if '回测结果' in line:
            return line.strip()
    return '无数据'


def parse_minute_summary(stdout):
    """从分钟回测 stdout 提取统计信息。"""
    lines = []
    capture = False
    for line in stdout.split('\n'):
        if '回测结果' in line:
            capture = True
            continue
        if capture and line.strip():
            if line.startswith('✅') or line.startswith('🦞'):
                break
            lines.append(line.strip())
    return '\n'.join(lines) if lines else '无数据'


def generate_summary_report(auction_ok, auction_out, minute_ok, minute_out, config, days):
    """生成汇总 Markdown 报告。"""
    today = datetime.date.today().strftime('%Y%m%d')
    out_path = OUT_DIR / f'backtest_summary_{today}.md'

    lines = []
    lines.append(f'# 龙虾回测汇总报告')
    lines.append(f'')
    lines.append(f'**生成时间**: {datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")}')
    lines.append(f'')
    lines.append(f'## 回测配置')
    lines.append(f'')
    lines.append(f'| 参数 | 值 |')
    lines.append(f'|------|-----|')
    lines.append(f'| 回测天数 | {days} 个交易日 |')
    lines.append(f'| 竞价涨幅阈值 | ≥{config.get("auction_threshold", {}).get("bid_increase_min", 3.0)}% |')
    lines.append(f'| 竞价量比阈值 | ≥{config.get("auction_threshold", {}).get("bid_volume_ratio", 1.05)} |')
    lines.append(f'| 开盘急拉 | {config.get("auction_threshold", {}).get("open_rise_timeout_min", 5)}min内≥{config.get("auction_threshold", {}).get("open_rise_pct", 3.0)}% |')
    lines.append(f'| 分钟量异动阈值 | ≥{config.get("minute_threshold", {}).get("volume_spike_ratio", 2.0)}x均量 |')
    lines.append(f'| 分钟价格突破 | 前{config.get("minute_threshold", {}).get("price_break_lookback", 5)}K最高 |')
    lines.append(f'| 持仓周期 | T+{config.get("minute_threshold", {}).get("hold_days", 3)} |')
    lines.append(f'')
    lines.append(f'## 竞价异动回测')
    lines.append(f'')
    if auction_ok:
        lines.append(f'**状态**: ✅ 成功')
        summary_line = parse_auction_summary(auction_out)
        lines.append(f'')
        lines.append(f'```')
        lines.append(summary_line)
        lines.append(f'```')
        lines.append(f'')
        lines.append(f'> 详细报告见 `reports/backtest_auction_{today}.md`')
    else:
        lines.append(f'**状态**: ❌ 失败')
        lines.append(f'')
    lines.append(f'')
    lines.append(f'## 分钟K线回测')
    lines.append(f'')
    if minute_ok:
        lines.append(f'**状态**: ✅ 成功')
        minute_summary = parse_minute_summary(minute_out)
        lines.append(f'')
        lines.append(f'```')
        lines.append(minute_summary)
        lines.append(f'```')
        lines.append(f'')
        lines.append(f'> 详细数据见 `reports/backtest_minute_signals.json`')
    else:
        lines.append(f'**状态**: ❌ 失败')
    lines.append(f'')
    lines.append(f'## 综合结论')
    lines.append(f'')
    if auction_ok and minute_ok:
        lines.append(f'- 竞价异动回测和分钟K线回测均已完成。')
        lines.append(f'- 建议结合两份详细报告交叉验证信号质量。')
    elif auction_ok:
        lines.append(f'- 竞价异动回测完成，分钟K线回测失败，请检查 thsdk 分钟K线数据权限。')
    elif minute_ok:
        lines.append(f'- 分钟K线回测完成，竞价异动回测失败，请检查 thsdk 分时数据权限。')
    else:
        lines.append(f'- 两个回测均失败，请确认 thsdk 已正确配置且数据权限可用。')
    lines.append(f'')
    lines.append(f'> 注意：thsdk 游客模式对历史数据可能有限制，部分日期/标的可能因数据不足被跳过。')

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    report = '\n'.join(lines)
    with open(out_path, 'w', encoding='utf-8') as f:
        f.write(report)
    return out_path


def main():
    parser = argparse.ArgumentParser(description='龙虾回测执行器')
    parser.add_argument('--days', type=int, default=None, help='回测最近N个交易日')
    parser.add_argument('--code', type=str, default=None, help='指定单只股票')
    parser.add_argument('--auction-only', action='store_true', help='仅运行竞价回测')
    parser.add_argument('--minute-only', action='store_true', help='仅运行分钟K线回测')
    args = parser.parse_args()

    config = load_config()
    days = args.days or config.get('default_days', 60)

    print(f'🦞 龙虾回测执行器 v1.0 | 回测 {days} 个交易日')
    print(f'{"="*50}')

    run_auction = not args.minute_only
    run_minute = not args.auction_only

    auction_ok, auction_out, auction_err = True, '', ''
    minute_ok, minute_out, minute_err = True, '', ''

    if run_auction:
        auction_ok, auction_out, auction_err = run_auction_backtest(days, args.code)

    if run_minute:
        minute_ok, minute_out, minute_err = run_minute_backtest(days, args.code)

    # 生成汇总报告
    report_path = generate_summary_report(auction_ok, auction_out, minute_ok, minute_out, config, days)
    print(f'\n{"="*50}')
    print(f'✅ 汇总报告已写入 {report_path}')

    # 最终状态
    passed = (not run_auction or auction_ok) and (not run_minute or minute_ok)
    if passed:
        print('✅ 全部回测完成')
        sys.exit(0)
    else:
        print('⚠️  部分回测失败，请查看报告了解详情')
        sys.exit(1)


if __name__ == '__main__':
    main()
