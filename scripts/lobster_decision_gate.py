#!/usr/bin/env python3
"""
龙虾决策网关 v1.0 — 冰点防御闭环核心
依据盘前报告 + 竞价异动 + 分钟K线信号，输出当日交易决策开关。

输入：最近一份 reports/盘前选股_*.md + trading/auction_anomaly.json + trading/minute_signals.json
输出：trading/decision_flags.json

用法：
  python3 scripts/lobster_decision_gate.py [--mode auto]  # 自动读取最新盘前报告
  python3 scripts/lobster_decision_gate.py --report reports/盘前选股_2026-07-08.md  # 指定报告
"""

import json
import re
import sys
import datetime
import argparse
from pathlib import Path

ROOT = Path(__file__).parent.parent
CONFIG_PATH = ROOT / 'lobster-config.json'
OUT_PATH = ROOT / 'trading' / 'decision_flags.json'


def load_risk_config():
    """从 lobster-config.json 读取 risk_control 配置节"""
    defaults = {
        'hard_stop_pct': -7.0,
        'stop_warning_pct': -5.0,
        'trailing_stop_pct': -3.0,
        'trailing_profit_threshold_pct': 5.0,
        'new_order_frozen_on_ice_point': True,
        'max_position_count_on_ice_point': 0,
    }
    if CONFIG_PATH.exists():
        try:
            with open(CONFIG_PATH) as f:
                cfg = json.load(f)
            return cfg.get('risk_control', defaults)
        except Exception:
            pass
    return defaults


def find_latest_premarket_report():
    """查找 reports/ 下最新的盘前选股报告"""
    reports_dir = ROOT / 'reports'
    candidates = list(reports_dir.glob('盘前选股_*.md')) + list(reports_dir.glob('盘前选股*.md'))
    if not candidates:
        return None
    candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return candidates[0]


def parse_premarket_report(report_path):
    """
    解析盘前选股报告，提取：
    - 仓位建议（空仓 / ≤1成 / 正常）
    - 上涨家数 / 情绪判断
    - 各维度候选标的及锁定状态
    """
    if not report_path or not Path(report_path).exists():
        return {}

    text = Path(report_path).read_text(encoding='utf-8')
    result = {
        'up_count': 0,
        'emotion_label': '',
        'position_advice': '正常',
        'is_ice_point': False,
        'ice_reason': '',
        'stocks': {},
    }

    # 提取上涨家数
    m = re.search(r'(\d+)\s*涨.*?(\d+)\s*跌', text)
    if m:
        result['up_count'] = int(m.group(1))

    # 判断冰点
    up = result['up_count']

    # 从文本中检测仓位建议关键词
    if '空仓' in text:
        result['position_advice'] = '空仓'
        result['is_ice_point'] = True
        result['ice_reason'] = f'极端冰点·上涨仅{up}家，盘前建议空仓'
    elif '≤1成' in text or '≤1成' in text or '1成' in text:
        result['position_advice'] = '≤1成'
        result['is_ice_point'] = True
        result['ice_reason'] = f'冰点·上涨仅{up}家，仓位上限1成'
    elif up < 1600:
        result['position_advice'] = '≤1成'
        result['is_ice_point'] = True
        result['ice_reason'] = f'极端冰点·上涨不足{up}家'
    elif up < 2000:
        result['is_ice_point'] = True
        result['ice_reason'] = f'冰点区·上涨{up}家，≤1成分歧低吸暂停'
    elif up < 2500:
        result['emotion_label'] = '温和'
    elif up < 3500:
        result['emotion_label'] = '活跃'
    else:
        result['emotion_label'] = '高潮'

    # 解析个股锁定状态：从报告中提取 locked/observe 标记
    # 格式: "...(locked)" / "锁定原因：..." / "冰点·3.0熔断"
    # 提取3.0趋势低吸节的锁定信息
    in_30_section = False
    in_10_fo_section = False
    current_stock = {}

    for line in text.split('\n'):
        # 检测进入3.0趋势低吸
        if '3.0趋势低吸' in line:
            in_30_section = True
            in_10_fo_section = False
            continue
        if '1.0分歧低吸' in line or '1.0一进二' in line:
            in_30_section = False
            in_10_fo_section = True
            continue
        if '2.0板块卡位' in line or '板块卡位' in line:
            in_30_section = False
            in_10_fo_section = False
            continue

        if not (in_30_section or in_10_fo_section):
            continue

        # 解析个股行：名称(代码) — ...
        stock_match = re.match(r'.*?(\w[\u4e00-\u9fa5]+?)\((\d{6})\)', line)
        if stock_match:
            name = stock_match.group(1)
            code = stock_match.group(2)
            status = 'observe'
            reason = ''
            allow_buy = True

            if in_30_section:
                if '熔断' in line or 'locked' in line.lower():
                    status = 'locked'
                    reason = f'冰点·3.0熔断'
                    allow_buy = False
                elif '锁定' in line:
                    status = 'locked'
                    reason = '锁定'
                    allow_buy = False
                elif '辅助' in line and '1成' in line:
                    status = 'locked'
                    reason = '辅助模式·仅MA10低吸'
                    allow_buy = False

            if in_10_fo_section:
                # 冰点冻结一进二 / 分歧低吸
                if result['is_ice_point'] and '分歧低吸' in text:
                    if '分歧低吸' in line or (
                        stock_match and in_10_fo_section and result['up_count'] < 1600
                    ):
                        status = 'locked'
                        reason = '冰点冻结分歧低吸'
                        allow_buy = False

            result['stocks'][name] = {
                'code': code,
                'status': status,
                'reason': reason,
                'allow_buy': allow_buy,
            }

    return result


def load_auction_anomalies():
    """读取竞价异动文件，提取异常标的列表"""
    path = ROOT / 'trading' / 'auction_anomaly.json'
    if not path.exists():
        return set()
    try:
        with open(path) as f:
            data = json.load(f)
        codes = set()
        for a in data.get('anomalies', []):
            code = str(a.get('code', a.get('代码', '')))
            if code:
                codes.add(code)
        return codes
    except Exception:
        return set()


def generate_decision_flags(report_info, risk_config):
    """生成 decision_flags.json 内容"""
    now = datetime.datetime.now()

    up = report_info.get('up_count', 0)
    position_advice = report_info.get('position_advice', '正常')

    # 冻结判定
    frozen = False
    frozen_reason = ''

    if position_advice == '空仓':
        frozen = True
        frozen_reason = f'极端冰点·上涨仅{up}家，盘前建议空仓'
    elif position_advice == '≤1成':
        frozen = True
        frozen_reason = f'冰点·上涨{up}家，仓位上限1成'
    elif up < 1600:
        frozen = True
        frozen_reason = f'极端冰点·上涨不足{up}家'
    elif up < 2000:
        frozen = True
        frozen_reason = f'冰点区·上涨{up}家'

    if risk_config.get('new_order_frozen_on_ice_point', True):
        new_order_frozen = frozen
    else:
        new_order_frozen = False

    # 构建 stocks 字典
    stocks = {}
    for name, info in report_info.get('stocks', {}).items():
        stocks[name] = {
            'code': info.get('code', ''),
            'status': info.get('status', 'observe'),
            'reason': info.get('reason', ''),
            'allow_buy': info.get('allow_buy', True) and not new_order_frozen,
        }

    flags = {
        'timestamp': now.strftime('%Y-%m-%d %H:%M:%S'),
        'position_limit': position_advice,
        'new_order_frozen': new_order_frozen,
        'frozen_reason': frozen_reason if new_order_frozen else '',
        'stocks': stocks,
        'stop_loss_rules': {
            'hard_stop_pct': risk_config.get('hard_stop_pct', -7.0),
            'warning_pct': risk_config.get('stop_warning_pct', -5.0),
            'trailing_stop_pct': risk_config.get('trailing_stop_pct', -3.0),
            'trailing_profit_threshold_pct': risk_config.get('trailing_profit_threshold_pct', 5.0),
            'trailing_stop_enabled': True,
        },
    }

    return flags


def main():
    parser = argparse.ArgumentParser(description='龙虾决策网关')
    parser.add_argument('--report', type=str, help='指定盘前报告路径')
    parser.add_argument('--mode', default='auto', choices=['auto'], help='运行模式')
    args = parser.parse_args()

    print('🛡️  龙虾决策网关 v1.0')

    # 加载风险配置
    risk_config = load_risk_config()
    print(f'   风控: 硬止损{risk_config["hard_stop_pct"]}% / 预警{risk_config["stop_warning_pct"]}% / 移动止盈{risk_config["trailing_profit_threshold_pct"]}%→回撤{risk_config["trailing_stop_pct"]}%')

    # 定位盘前报告
    report_path = args.report if args.report else find_latest_premarket_report()
    if not report_path:
        print('❌ 找不到盘前选股报告')
        sys.exit(1)

    print(f'📄 盘前报告: {report_path}')

    # 解析
    report_info = parse_premarket_report(report_path)
    print(f'   上涨: {report_info.get("up_count", "?")}家')
    print(f'   仓位建议: {report_info["position_advice"]}')
    print(f'   冰点: {"是" if report_info["is_ice_point"] else "否"}')
    print(f'   标的数: {len(report_info["stocks"])}')

    # 生成决策
    flags = generate_decision_flags(report_info, risk_config)

    # 输出
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_PATH, 'w', encoding='utf-8') as f:
        json.dump(flags, f, ensure_ascii=False, indent=2)

    print(f'✅ 决策已写入 {OUT_PATH}')
    print(f'   新开仓: {"❌ 冻结" if flags["new_order_frozen"] else "✅ 允许"}')
    if flags['new_order_frozen']:
        print(f'   原因: {flags["frozen_reason"]}')

    # 打印锁定标的
    locked_stocks = {k: v for k, v in flags['stocks'].items() if not v['allow_buy']}
    if locked_stocks:
        print(f'   锁定标的 ({len(locked_stocks)}只):')
        for name, info in locked_stocks.items():
            print(f'     {name}({info["code"]}): {info["reason"]}')


if __name__ == '__main__':
    main()
