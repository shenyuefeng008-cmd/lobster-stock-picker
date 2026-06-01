#!/usr/bin/env python3
"""龙虾卖点检测器 v1.3 — 交易日计算读取统一配置"""

import json, subprocess, re, sys, datetime
from pathlib import Path

# ==================== 交易日计算工具 ====================
# 从统一配置文件读取节假日数据（不再hardcode）
_TRADING_CALENDAR_PATH = Path(__file__).parent.parent / 'config' / 'trading_calendar.json'

def _load_trading_calendar():
    """加载交易日历配置"""
    try:
        with open(_TRADING_CALENDAR_PATH) as f:
            data = json.load(f)
        return set(data.get('holidays', [])), set(data.get('adjusted_workdays', []))
    except Exception as e:
        print(f'[WARN] 无法读取交易日历配置: {e}，使用内置备用数据', file=sys.stderr)
        # 备用数据（与config/trading_calendar.json保持一致）
        return (
            {
    "2026-01-01","2026-01-02","2026-01-03",
    "2026-01-26","2026-01-27","2026-01-28","2026-01-29","2026-01-30","2026-01-31",
    "2026-02-01","2026-02-02","2026-02-03","2026-02-04",
    "2026-04-04","2026-04-05","2026-04-06",
    "2026-05-01","2026-05-02","2026-05-03","2026-05-04","2026-05-05",
    "2026-06-19","2026-06-20","2026-06-21",
    "2026-09-25","2026-09-26","2026-09-27",
    "2026-10-01","2026-10-02","2026-10-03","2026-10-04","2026-10-05","2026-10-06","2026-10-07",
            },
            {"2026-01-25","2026-02-08","2026-04-26","2026-09-28","2026-10-10"}
        )

_HOLIDAYS, _ADJUSTED = _load_trading_calendar()


def is_trading_day(d):
    """判断是否为A股交易日（不含周末和节假日）"""
    ds = d.isoformat()
    if ds in _HOLIDAYS:
        return False
    if ds in _ADJUSTED:
        return True
    return d.weekday() < 5  # 周一~周五

def count_trading_days(start_date, end_date):
    """计算两个日期之间的交易日天数（不含首日）"""
    count = 0
    d = start_date + datetime.timedelta(days=1)
    while d <= end_date:
        if is_trading_day(d):
            count += 1
        d += datetime.timedelta(days=1)
    return count

# ==================== 开盘时间验证 ====================
def is_trading_time():
    """检查当前是否在A股交易时间"""
    now = datetime.datetime.now()
    hm = now.strftime("%H:%M")
    
    if "09:15" <= hm < "09:30":
        return True
    if "09:30" <= hm < "11:30":
        return True
    if "13:00" <= hm < "15:00":
        return True
    return False

if not is_trading_time():
    print(f"⏸️ 非交易时间 ({datetime.datetime.now().strftime('%H:%M')})，卖点监控跳过")
    sys.exit(0)


sys.path.insert(0, str(Path(__file__).resolve().parent))
from simulated_trading import sell, status

# 配置（对齐lobster-rules.md v2.3 + 止盈体系）
STOP_LOSS_PCT_MAP = {
    '1.0一进二': -5.0,
    '1.0分歧低吸': -5.0,
    '2.0板块卡位': -7.0,
    '3.0趋势低吸': -3.0,
}
MAX_HOLD_DAYS = 5  # 最大持仓天数（1.0时间止损：第3个交易日未涨停）


# ==================== 其余代码不变 ====================

def get_realtime_quotes(codes):
    """批量获取实时行情，返回 {code: {price, pct}}"""
    if not codes:
        return {}
    
    ql = [f"sh{c}" if c.startswith('6') else f"sz{c}" for c in codes]
    r = subprocess.run(["curl", "-s", "--max-time", "10", f"https://qt.gtimg.cn/q={','.join(ql)}"], 
                      capture_output=True, timeout=12)
    
    for enc in ["gb2312", "gbk", "utf-8"]:
        try:
            txt = r.stdout.decode(enc)
            break
        except:
            continue
    else:
        txt = r.stdout.decode("utf-8", "replace")
    
    quotes = {}
    for line in txt.split(";"):
        m = re.search(r'v_(\w+)="([^"]*)"', line)
        if m:
            p = m.group(2).split("~")
            if len(p) > 3:
                code = p[2]
                try:
                    quotes[code] = {
                        'price': float(p[4]),  # p[4]=当前价, p[3]=昨收
                        'pct': float(p[32]) if len(p) > 32 else 0
                    }
                except (ValueError, IndexError):
                    continue
    return quotes

def detect_sellpoint(position, current_price):
    """检测卖点，返回 (reason, None) 或 (None, error)"""
    buy_price = position['buy_price']
    buy_date = datetime.datetime.strptime(position['buy_date'], '%Y-%m-%d').date()
    hold_days = count_trading_days(buy_date, datetime.date.today())  # ✅ 交易日计算
    dimension = position.get('dimension', '')
    name = position.get('name', '')
    code = position.get('code', '')
    
    pnl_pct = (current_price - buy_price) / buy_price * 100
    
    # === 按维度止损（对齐lobster-rules.md v2.3）===
    
    # 1.0硬止损：买入价-5% 或 时间止损（第3天未涨停）
    if '1.0' in dimension:
        # 时间止损：第3个交易日未涨停
        if hold_days >= 3 and abs(current_price - buy_price) / buy_price < 0.098:
            return f"1.0时间止损：持仓{hold_days}天未涨停，次日竞价卖出", None
        # 硬止损
        sl_pct = STOP_LOSS_PCT_MAP.get(dimension, -5.0)
        if pnl_pct <= sl_pct:
            return f"1.0硬止损：回撤{pnl_pct:.2f}% ≤ {sl_pct:.0f}%（买入价×0.95）", None
    
    # 2.0硬止损：买入价-7%
    if '2.0' in dimension and pnl_pct <= STOP_LOSS_PCT_MAP.get(dimension, -7.0):
        sl_pct = STOP_LOSS_PCT_MAP.get(dimension, -7.0)
        return f"2.0硬止损：回撤{pnl_pct:.2f}% ≤ {sl_pct:.0f}%（买入价×0.93）", None
    
    # 3.0：技术止损MA5<MA10（主）+ %止损（备用）
    if '3.0' in dimension:
        if pnl_pct <= -3.0:
            return f"3.0窄止损：回撤{pnl_pct:.2f}% ≤ -3%", None
    
    # === 止盈 ===
    # 1.0/2.0不在这里判断分时止盈（盘中由CRON_SELLPOINT_TASK的分时追踪判断）
    # 收盘复盘中只执行止损，止盈在盘中完成
    
    # 3.0 Tier-1退出检查（收盘复盘完整执行）
    if '3.0' in dimension and pnl_pct > 10:
        # 这里检查催化兑现/板块分化，简化版输出提示
        return f"3.0 Tier-1止盈观察：浮盈{pnl_pct:.1f}% > 10%，收盘时检查催化兑现/板块分化", None
    
    # 时间止损（持仓超过N天）
    if hold_days >= MAX_HOLD_DAYS:
        return f"时间止损：持仓{hold_days}天 ≥ {MAX_HOLD_DAYS}天", None
    
    return None, f"未触发卖点（盈亏{pnl_pct:+.2f}%，持仓{hold_days}天）"

def run():
    """主函数：检测所有持仓的卖点"""
    # 加载持仓
    with open(Path(__file__).resolve().parent.parent / "trading" / "模拟持仓.json") as f:
        data = json.load(f)
    
    if not data['positions']:
        print("📋 无持仓，无需检测卖点")
        return
    
    # 获取所有可卖出持仓的代码
    sellable = [p for p in data['positions'] if p['can_sell']]
    if not sellable:
        print("📋 无可卖出持仓（T+1锁定）")
        return
    
    codes = [p['code'] for p in sellable]
    quotes = get_realtime_quotes(codes)
    
    if not quotes:
        print("⚠️ 获取实时行情失败")
        return
    
    # 逐持仓检测卖点
    triggers = []
    for pos in sellable:
        code = pos['code']
        name = pos['name']
        
        if code not in quotes:
            print(f"  ⚠️ {name}({code}) 行情获取失败，跳过")
            continue
        
        current_price = quotes[code]['price']
        reason, err = detect_sellpoint(pos, current_price)
        
        if reason:
            # 触发卖点，执行卖出
            sell_type = "止损" if '止损' in reason else "止盈"
            result = sell(code, current_price, reason, sell_type)
            triggers.append(f"🔴 卖出 {name}({code}): {reason}")
            print(f"   {result}")
        else:
            print(f"  {name}({code}) 未触发: {err}")
    
    # 输出结果
    if triggers:
        print(f"\n📊 卖点触发 {len(triggers)} 只:")
        for t in triggers:
            print(t)
    else:
        print("\n✅ 无卖点触发")
    
    # 输出当前状态
    print(f"\n{status()}")

if __name__ == '__main__':
    run()
