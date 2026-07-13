#!/usr/bin/env python3
"""龙虾盘中巡检 v1.0 — 统一买卖点监控（合并原买点/卖点/尾盘3个任务）

调度：
  10:00,10:30,13:00,13:30,14:00,14:30 → 常规巡检
  14:45 → 尾盘专项（加情绪定调+异动扫描）
  14:50 → 超短卖点预警（涨停次日未封板→卖出）

逻辑：一次采集 → 先卖后买 → 统一输出
"""

import json, subprocess, re, sys, datetime, os, requests
from pathlib import Path
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed

# 华泰证券行情 API（主数据源，优先使用；getQuote 直接返回涨停价/停牌状态，更可靠）
_HT_APIKEY = os.environ.get("HT_APIKEY", "ht_Xk9B8h2pRsT6WAUSwwn6GvWbCwwAS0xVp9rFGzgAv")
_HT_GET_QUOTE_URL = "https://ai.zhangle.com/edge/entry/gate/api/simSkills/getQuote"
_HT_SKILL_CODE = "mx_1778741794549"
_HT_TIMEOUT = 3  # 单票超时（秒），多票并发总耗时可控

# westock-data 兜底数据源（补充 vol/high/low/name 等 HT 不提供的字段）
_NODE = '/usr/local/bin/node'

_WESTOCK_SCRIPT = os.path.expanduser(
    "~/.qclaw/skills/westock-data/scripts/index.js"
)

# ==================== 开盘时间验证 ====================
def is_trading_hours():
    now = datetime.datetime.now()
    hm = now.strftime("%H:%M")
    return ("09:15" <= hm < "09:30" or "09:30" <= hm < "11:30" or "13:00" <= hm < "15:00")

if not is_trading_hours():
    print(f"⏸️ 非交易时间 ({datetime.datetime.now().strftime('%H:%M')})，巡检跳过")
    sys.exit(0)

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))
from simulated_trading import buy, sell, status as trade_status

# ==================== 配置 ====================
CANDIDATES_PATH = str(BASE.parent / "trading" / "watchlist_candidates.json")
POSITIONS_PATH = BASE.parent / "trading" / "模拟持仓.json"

# 止损线从lobster-config.json读取，支持动态微调
_CONFIG_PATH = Path(__file__).resolve().parent.parent / 'lobster-config.json'
def _load_stop_loss():
    try:
        with open(_CONFIG_PATH) as f:
            cfg = json.load(f)
        sl = cfg.get('stop_loss', {})
        return {
            '1.0一进二': sl.get('1.0', {}).get('hard_stop_pct', -7.0),
            '1.0分歧低吸': sl.get('1.0', {}).get('hard_stop_pct', -7.0),
            '2.0板块卡位': sl.get('2.0', {}).get('hard_stop_pct', -7.0),
            '3.0趋势低吸': -3.0,
        }
    except:
        return {'1.0一进二': -7.0, '1.0分歧低吸': -7.0, '2.0板块卡位': -7.0, '3.0趋势低吸': -3.0}
STOP_LOSS = _load_stop_loss()

def _load_take_profit_config():
    """从lobster-config.json读取分时止盈配置"""
    try:
        with open(_CONFIG_PATH) as f:
            cfg = json.load(f)
        return cfg.get('intraday_take_profit', {})
    except:
        return {'min_profit_pct': 5.0, 'callback_threshold_pct': 5.0}
MAX_HOLD_DAYS = 5
BASE_POSITION_PCT = {'1.0分歧低吸': 10, '1.0一进二': 10, '2.0板块卡位': 10, '3.0趋势低吸': 15}

CONFIG_PATH = BASE.parent / "lobster-config.json"

def load_emotion_matrix():
    """从config加载情绪矩阵"""
    try:
        with open(CONFIG_PATH) as f:
            cfg = json.load(f)
        return cfg.get('emotion', {})
    except:
        return {}

def get_emotion_tier(up_count, matrix):
    """根据涨跌家数返回 (tier_key, pos_limit, dominant_dim)"""
    if not matrix:
        return None, 10, '1.0'
    if up_count < 1500:
        tier = matrix.get('below_1500', {})
    elif up_count < 2000:
        tier = matrix.get('1500_2000', {})
    elif up_count < 2500:
        tier = matrix.get('2000_2500', {})
    elif up_count < 3500:
        tier = matrix.get('2500_3500', {})
    else:
        tier = matrix.get('above_3500', {})
    return tier.get('dim','1.0'), tier.get('pos_limit_pct', 50), tier.get('dim','1.0')

def emotion_triple_check(base_dim, base_pos_limit, today_up, yesterday_up, today_volume=None, yesterday_volume=None):
    """情绪三重校验（v2.5规则）
    base_dim/base_pos_limit: 基础判定结果
    today_up/yesterday_up: 今日/昨日涨跌家数
    today_volume/yesterday_volume: 今日/昨日成交额（可选，用于缩量修正）
    
    返回: (修正后dim, 修正后pos_limit, 修正说明列表)
    """
    corrections = []
    dim = base_dim
    pos_limit = base_pos_limit
    
    # 维度降级顺序：2.0+1.0 → 1.0+3.0 → 1.0 → 辅助模式
    dim_order = ['2.0+1.0', '1.0+3.0', '1.0']
    dim_pos_map = {'2.0+1.0': 7, '1.0+3.0': 9, '1.0': 5}
    
    # 校验1：剧烈波动日（今日较前日变化>1500）
    if yesterday_up and yesterday_up > 0:
        delta = abs(today_up - yesterday_up)
        if delta > 1500:
            # 降一级：找当前维度在降级顺序中的前一个
            try:
                idx = dim_order.index(dim) if dim in dim_order else len(dim_order)
                if idx < len(dim_order) - 1:
                    new_dim = dim_order[idx + 1]
                    new_pos = dim_pos_map.get(new_dim, pos_limit)
                else:
                    new_dim = dim  # 已经最低
                    new_pos = min(pos_limit, 30)  # 极端保守，最低30%
                corrections.append(f"剧烈波动日(delta={delta}), {dim}→{new_dim}, 仓位{pos_limit}%→{new_pos}%")
                dim = new_dim
                pos_limit = new_pos
            except:
                pass
    
    # 校验2：缩量修正（今日成交额<前日，不得升级只能维持或降级）
    if today_volume and yesterday_volume and yesterday_volume > 0:
        if today_volume < yesterday_volume:
            # 如果基础判定已升级（vs昨日），则降回
            corrections.append(f"缩量修正(今{today_volume/1e8:.0f}亿<昨{yesterday_volume/1e8:.0f}亿), 禁止升级")
            # 缩量时仓位上限额外收紧10%
            pos_limit = max(pos_limit - 10, 10)
    
    # 校验3：极端值校验（涨跌家数>4000或<500触发预警）
    if today_up > 4000 or today_up < 500:
        corrections.append(f"⚠️ 极端值预警(涨跌{today_up}), 需人工确认数据有效性")
        # 极端值时保守处理：仓位减半
        pos_limit = max(pos_limit // 2, 10)
    
    return dim, pos_limit, corrections

def adjust_position_pct(base_pct, pos_limit_pct, used_count):
    """根据情绪矩阵动态调整仓位比例
    
    pos_limit_pct: 总仓位上限（单位：%，如30表示30%）
    base_pct: 维度基础单仓比例（单位：%，如10表示10%）
    used_count: 当前持仓数量
    
    return: 本次可买单仓比例（单位：%）
    """
    # 已持仓数量达到上限
    max_stocks = int(pos_limit_pct / base_pct)
    if used_count >= max_stocks:
        return 0
    
    # 剩余额度（%）= 总上限% - 已用%
    # 简化：假设已持都是base_pct，实际应该读持仓文件计算
    remaining_pct = pos_limit_pct - used_count * base_pct
    if remaining_pct <= 0:
        return 0
    
    # 单仓上限 = min(维度基准, 剩余额度)
    return round(min(base_pct, remaining_pct), 1)

# ==================== 数据采集（一次完成） ====================
def fetch_emotion():
    """获取实时涨跌家数（via westock-data changedist）"""
    try:
        r = subprocess.run(
            [_NODE, _WESTOCK_SCRIPT, "changedist", "hs"],
            capture_output=True, text=True, timeout=15
        )
        out = r.stdout.strip()
        # westock 返回 Markdown 表格，提取 上涨/下跌/涨停/跌停 列（跳过平盘）
        m = re.search(r'沪深[| ]+\S+[| ]+\S+[| ]+(\d+)[| ]+(\d+)[| ]+\d+[| ]+(\d+)[| ]+(\d+)', out)
        if m:
            return {
                'up': int(m.group(1)),
                'down': int(m.group(2)),
                'zt': int(m.group(3)),
                'dt': int(m.group(4))
            }
        # fallback: 尝试 JSON（旧版兼容）
        data = json.loads(out)
        if isinstance(data, dict):
            return {
                'up': data.get('up', 0),
                'down': data.get('down', 0),
                'zt': data.get('zt', 0),
                'dt': data.get('dt', 0)
            }
    except Exception as e:
        print(f"⚠️ westock-data 涨跌分布获取失败: {e}", file=sys.stderr)
    return None

def _code_to_exchange(code):
    """根据股票代码推断交易所"""
    if code.startswith('6'):
        return 'SH'
    elif code.startswith('0') or code.startswith('3'):
        return 'SZ'
    elif code.startswith('4') or code.startswith('8'):
        return 'BJ'
    return None

def _load_price_guard():
    """从 lobster-config.json 读取 price_guard 配置，兜底使用默认值"""
    defaults = {
        'max_deviation_from_close': 0.10,
        'min_multiplier_of_open': 0.95,
        'reject_on_stale_price': True,
    }
    try:
        with open(_CONFIG_PATH) as f:
            cfg = json.load(f)
        return cfg.get('price_guard', defaults)
    except:
        return defaults

PRICE_GUARD = _load_price_guard()

def fetch_quotes_ht(codes):
    """华泰行情API（主数据源）：并发获取 price/pct/limit_up/is_suspended，更可靠
    v1.2: 新增幻影价校验 — 用昨收价（limitUp/1.10）交叉验证，过滤 stale 数据和极端异常值
    """
    if not codes:
        return {}
    quotes = {}

    def _fetch_one(code):
        exchange = _code_to_exchange(code)
        if not exchange:
            return code, None
        try:
            resp = requests.post(
                _HT_GET_QUOTE_URL,
                json={'stockCode': code, 'exchange': exchange},
                headers={
                    'apiKey': _HT_APIKEY,
                    'Content-Type': 'application/json',
                    'skillCode': _HT_SKILL_CODE,
                },
                timeout=_HT_TIMEOUT,
            )
            data = resp.json()
            if data.get('ok') and data.get('data'):
                d = data['data']
                price = float(d.get('currentPrice', 0))
                pct = float(d.get('change', 0))
                limit_up = float(d.get('limitUp', 0))
                limit_down = float(d.get('limitDown', 0))

                # ── 幻影价防护 v1.2 ──
                if limit_up > 0 and PRICE_GUARD.get('reject_on_stale_price', True):
                    est_close = round(limit_up / 1.10, 2)
                    max_dev = PRICE_GUARD.get('max_deviation_from_close', 0.10)

                    # 检查1: 价格是否等于昨收价（stale数据，特别是高开股开盘瞬间）
                    is_stale = (abs(price - est_close) < 0.01 and abs(pct) < 0.01)
                    # 检查2: 价格是否超出昨收 ± max_dev 范围（极端异常值）
                    out_of_range = (price < est_close * (1 - max_dev) or price > est_close * (1 + max_dev))

                    if is_stale or out_of_range:
                        print(f"⚠️ 华泰价格校验失败({code}): price={price}, est_昨收={est_close}, "
                              f"pct={pct}%, stale={is_stale}, outlier={out_of_range} → 降级到westock", file=sys.stderr)
                        return code, None

                return code, {
                    'price': price,
                    'pct': pct,
                    'limit_up': limit_up,
                    'limit_down': limit_down,
                    'is_suspended': d.get('isSuspended', False),
                }
        except Exception as e:
            print(f"⚠️ 华泰行情获取失败({code}): {e}", file=sys.stderr)
        return code, None

    with ThreadPoolExecutor(max_workers=min(len(codes), 10)) as executor:
        futures = {executor.submit(_fetch_one, code): code for code in codes}
        for future in as_completed(futures, timeout=_HT_TIMEOUT * 2 + 2):
            code, result = future.result()
            if result:
                quotes[code] = result

    return quotes

def fetch_quotes(codes):
    """获取实时行情（华泰优先 + westock兜底），返回 {code: {price, pct, vol, high, low, name, limit_up, is_suspended}}"""
    if not codes:
        return {}

    quotes = {}
    # 1. 华泰API优先：获取 price/pct/limit_up/is_suspended（更可靠，直接给涨停价）
    ht_quotes = fetch_quotes_ht(codes)
    ht_ok = len(ht_quotes)

    # 2. westock-data兜底：获取 vol/high/low/name 等补充字段
    ql = [f"sh{c}" if c.startswith('6') else f"sz{c}" for c in codes]
    ws_ok = 0
    try:
        r = subprocess.run(
            [_NODE, _WESTOCK_SCRIPT, "quote", ",".join(ql)],
            capture_output=True, text=True, timeout=15
        )
        data = json.loads(r.stdout)
        items = data if isinstance(data, list) else list(data.values()) if isinstance(data, dict) else []
        ws_ok = len(items)
        for item in items:
            code_raw = item.get("code", "")
            code = code_raw[2:] if len(code_raw) > 2 else code_raw
            ht = ht_quotes.get(code, {})
            ws_price = float(item.get("price", 0))
            quotes[code] = {
                # price/pct 优先华泰（涨停封死后不返回脏数据），华泰不可用才用westock
                'price': ht.get('price') or ws_price,
                'pct': ht.get('pct') if ht.get('pct') is not None else float(item.get("pctChg", 0)),
                # 华泰专用字段
                'limit_up': ht.get('limit_up', 0),
                'limit_down': ht.get('limit_down', 0),
                'is_suspended': ht.get('is_suspended', False),
                # 补充字段（华泰不提供，走westock）
                'vol': float(item.get("volume", 0)),
                'high': float(item.get("high", 0)),
                'low': float(item.get("low", 0)),
                'name': item.get("name", ""),
            }
    except Exception as e:
        print(f"⚠️ westock-data 行情获取失败: {e}", file=sys.stderr)
        # westock也挂了，纯华泰数据
        for code in codes:
            ht = ht_quotes.get(code, {})
            if ht:
                quotes[code] = {
                    'price': ht.get('price', 0),
                    'pct': ht.get('pct', 0),
                    'vol': 0, 'high': 0, 'low': 0, 'name': '',
                    'limit_up': ht.get('limit_up', 0),
                    'limit_down': ht.get('limit_down', 0),
                    'is_suspended': ht.get('is_suspended', False),
                }

    # 数据源状态摘要
    if ht_ok == 0 and ws_ok > 0:
        print(f"⚠️ 华泰API不可用，已降级到westock-data（{ws_ok}只）")
    elif ht_ok > 0:
        print(f"📊 行情: 华泰{ht_ok}只 + westock{ws_ok}只")
    return quotes

def _fetch_open_price_qt(code):
    """从腾讯行情 API 获取股票今日开盘价（parts[5]=今开）
    用于交叉验证华泰API返回的价格是否合理（高开股开盘瞬间可能返回昨收价）
    """
    try:
        prefix = 'sh' if code.startswith('6') else 'sz'
        url = f'https://qt.gtimg.cn/q={prefix}{code}'
        from urllib.request import urlopen
        raw = urlopen(url, timeout=3).read()
        txt = raw.decode('gbk', errors='replace')
        for line in txt.strip().split('\n'):
            if 'v_' in line:
                parts = line.split('"')[1].split('~')
                if len(parts) > 5 and parts[3]:
                    return float(parts[3])
    except Exception as e:
        print(f"⚠️ 腾讯开盘价获取失败({code}): {e}", file=sys.stderr)
    return None

def fetch_kline(code, days=10):
    """获取K线数据（via westock-data）"""
    prefix = 'sh' if code.startswith('6') else 'sz'
    try:
        r = subprocess.run(
            [_NODE, _WESTOCK_SCRIPT, "kline", f"{prefix}{code}", "--period", "day", "--limit", str(days)],
            capture_output=True, text=True, timeout=15
        )
        data = json.loads(r.stdout)
        klines = data if isinstance(data, list) else []
        result = []
        for k in klines:
            result.append({
                'date': k.get('date', k.get('tradeDate', '')),
                'open': float(k.get('open', 0)),
                'close': float(k.get('close', 0)),
                'high': float(k.get('high', 0)),
                'low': float(k.get('low', 0)),
                'volume': float(k.get('volume', 0)),
            })
        return result
    except Exception as e:
        print(f"⚠️ westock-data K线获取失败({code}): {e}", file=sys.stderr)
    return []

def calc_ma(klines, period):
    if len(klines) < period: return None
    return sum(k['close'] for k in klines[-period:]) / period

# ==================== 风控配置加载 ====================
def _load_risk_control():
    """从 lobster-config.json 读取 risk_control 节，兜底使用默认值"""
    defaults = {
        'hard_stop_pct': -7.0,
        'stop_warning_pct': -5.0,
        'trailing_stop_pct': -3.0,
        'trailing_profit_threshold_pct': 5.0,
        'new_order_frozen_on_ice_point': True,
        'max_position_count_on_ice_point': 0,
    }
    try:
        with open(_CONFIG_PATH) as f:
            cfg = json.load(f)
        return cfg.get('risk_control', defaults)
    except:
        return defaults


# ==================== 卖点检测 ====================
def detect_sellpoints(positions, quotes):
    """检测所有持仓卖点，返回 (triggers, stop_statuses)：
    triggers: [(code, name, reason, action)]
    stop_statuses: {code: {status, pnl_pct, price, buy_price}}"""
    triggers = []
    stop_statuses = {}
    risk = _load_risk_control()
    hard_stop = risk['hard_stop_pct']          # -7.0
    stop_warn = risk['stop_warning_pct']        # -5.0
    trail_stop = risk['trailing_stop_pct']      # -3.0
    trail_thresh = risk['trailing_profit_threshold_pct']  # 5.0

    sellable = [p for p in positions if p.get('can_sell')]
    if not sellable:
        return triggers, stop_statuses

    for pos in sellable:
        code = pos['code']
        name = pos['name']
        q = quotes.get(code)
        if not q or q['price'] == 0:
            stop_statuses[code] = {
                'name': name, 'status': '数据缺失', 'pnl_pct': 0,
                'price': 0, 'buy_price': float(pos['buy_price'])
            }
            continue
        buy_price = float(pos['buy_price'])
        pnl_pct = (q['price'] - buy_price) / buy_price * 100
        dim = pos.get('dimension', '')
        hold_days = (datetime.date.today() - datetime.datetime.strptime(pos['buy_date'], '%Y-%m-%d').date()).days

        reason = None
        stop_status = '正常'

        # ── 阶梯止损判定（优先级从高到低）──

        # 🔴 -7% 硬止损（最高优先级）
        if pnl_pct <= hard_stop:
            reason = f"🔴 强制止损：亏损{pnl_pct:.1f}% ≤ {hard_stop}%（成本{buy_price:.2f}→现价{q['price']:.2f}）"
            stop_status = '强制止损'

        # ⚠️ -5% 预警（不自动卖出，但标记提醒）
        elif pnl_pct <= stop_warn and not reason:
            stop_status = '止损预警'

        # 📉 移动止盈：盈利 > trail_thresh%，从日内最高点回撤 > |trail_stop|%
        if not reason and pnl_pct > 0:
            day_high = q.get('high', q['price'])
            if day_high > 0 and day_high > buy_price:
                peak_pct = (day_high - buy_price) / buy_price * 100  # 日内最高盈利%
                if peak_pct >= trail_thresh:
                    drawdown = peak_pct - pnl_pct  # 从高点回撤的百分点
                    if drawdown >= abs(trail_stop):
                        reason = f"📉 移动止盈触发：最高盈利{peak_pct:.1f}%，回撤{drawdown:.1f}%≥{abs(trail_stop)}%"
                        stop_status = '移动止盈触发'

        # ── 原有止损逻辑（在阶梯止损未触发时继续生效）──

        # 1.0/2.0 硬止损（兼容旧 STOP_LOSS 配置）
        if not reason:
            sl = STOP_LOSS.get(dim, -5.0)
            if pnl_pct <= sl:
                reason = f"{dim}硬止损：回撤{pnl_pct:.2f}% ≤ {sl:.0f}%"

        # 1.0 时间止损
        if not reason and '1.0' in dim and hold_days >= 3 and pnl_pct < 9.8:
            reason = f"1.0时间止损：持仓{hold_days}个交易日未涨停"

        # 3.0 窄止损
        if not reason and '3.0' in dim and pnl_pct <= -3.0:
            reason = f"3.0窄止损：回撤{pnl_pct:.2f}%"

        # 3.0 MA5<MA10 技术止损
        if not reason and '3.0' in dim:
            klines = fetch_kline(code, 12)
            ma5 = calc_ma(klines, 5)
            ma10 = calc_ma(klines, 10)
            if ma5 and ma10 and ma5 < ma10:
                reason = f"3.0技术止损：MA5({ma5:.2f})<MA10({ma10:.2f})"

        # 超短卖点（14:50后，涨停次日未封板）
        now_min = datetime.datetime.now().hour * 60 + datetime.datetime.now().minute
        if not reason and now_min >= 890 and '1.0' in dim:
            buy_date_str = pos.get('buy_date', '')
            was_limit_up_yesterday = False
            if buy_date_str:
                try:
                    klines = fetch_kline(code, 5)
                    if len(klines) >= 2:
                        yesterday_close = klines[-2]['close']
                        day_before_close = klines[-3]['close'] if len(klines) >= 3 else klines[-2]['open']
                        if day_before_close > 0:
                            yesterday_pct = (yesterday_close - day_before_close) / day_before_close * 100
                            was_limit_up_yesterday = yesterday_pct >= 9.5
                except:
                    pass
            if was_limit_up_yesterday and q['pct'] < 7:
                reason = f"超短卖点：涨停次日未封板(昨涨≥9.5%,现{q['pct']:.1f}%)"

        # 分时止盈（兼容旧配置）
        if not reason and pnl_pct > 0:
            tp_cfg = _load_take_profit_config()
            if pnl_pct >= tp_cfg.get('min_profit_pct', 5.0) and hold_days >= 1:
                day_high = q.get('high', q['price'])
                if day_high > 0 and day_high > buy_price:
                    peak_pct = (day_high - buy_price) / buy_price * 100
                    callback_pct = peak_pct - pnl_pct
                    if callback_pct >= tp_cfg.get('callback_threshold_pct', 5.0):
                        reason = f"分时止盈：最高盈利{peak_pct:.1f}%回落{callback_pct:.1f}%≥{tp_cfg['callback_threshold_pct']}%"

        # 通用时间止损
        if not reason and hold_days >= MAX_HOLD_DAYS:
            reason = f"时间止损：持仓{hold_days}个交易日 ≥ {MAX_HOLD_DAYS}个交易日"

        if reason:
            if '止损' in reason:
                sell_type_val = "止损"
            elif pnl_pct < 0:
                sell_type_val = "止损"
            else:
                sell_type_val = "止盈"
            sell(code, q['price'], reason, sell_type_val)
            triggers.append((code, name, reason, 'SELL'))

        # 记录止损状态（所有持仓）
        stop_statuses[code] = {
            'name': name,
            'status': stop_status,
            'pnl_pct': round(pnl_pct, 2),
            'price': q['price'],
            'buy_price': buy_price,
        }

    return triggers, stop_statuses

# ==================== 买点检测 ====================
def detect_buypoints(candidates, quotes, emotion, minute_signals=None, decision_flags=None):
    """检测买点，返回 [(code, name, reason, action)]"""
    triggers = []
    positions = []  # 初始化持仓列表
    if not candidates:
        return triggers

    up_count = emotion.get('up', 0) if emotion else 0
    if up_count <= 0:
        return triggers  # 数据不可用，保守跳过

    # 情绪矩阵驱动
    emotion_matrix = load_emotion_matrix()
    dominant_dim, pos_limit, _ = get_emotion_tier(up_count, emotion_matrix)
    
    # 情绪三重校验（v2.5）
    state_path = BASE.parent / "trading" / "系统状态.json"
    yesterday_up = None
    try:
        with open(state_path) as sf:
            state = json.load(sf)
        yesterday_up = state.get('yesterday', {}).get('up_count')
    except:
        pass
    dominant_dim, pos_limit, corrections = emotion_triple_check(
        dominant_dim, pos_limit, up_count, yesterday_up)
    if corrections:
        print(f"🔧 情绪三重校验修正: {'; '.join(corrections)}")
    
    print(f"🎮 情绪矩阵: {up_count}涨 → 主导{dominant_dim}, 仓位上限{pos_limit}%")

    # 极冰点保护：<800涨时不做分歧低吸（接飞刀风险极高）
    extreme_freeze = up_count < 800

    for dim in ['1.0分歧低吸', '2.0板块卡位', '3.0趋势低吸']:
        for item in candidates.get(dim, []):
            code = str(item.get('代码', item.get('code', '')))
            name = item.get('名称', item.get('name', ''))
            if not code or code not in quotes:
                continue
            # 盘中实时解锁3.0：盘前打熔断标签，但盘中实时进入推理区/严格解锁则自动解除锁定
            is_30_melt = (item.get('locked') and '熔断' in item.get('锁定原因', ''))
            # 读配置
            cfg_30 = {}
            try:
                with open(CONFIG_PATH) as _f:
                    _cfg = json.load(_f)
                    cfg_30 = _cfg.get('3.0_emotion_rules', {})
            except: pass
            melt_below = cfg_30.get('melt_below', 1800)
            infer_zone = cfg_30.get('inference_zone', {})
            infer_low = infer_zone.get('low', 1800)
            infer_high = infer_zone.get('high', 2500)
            full_above = cfg_30.get('full_activate_above', 2500)
            # 判断解锁状态
            in_infer_zone = infer_low <= up_count <= infer_high
            in_full_unlock = up_count > full_above
            realtime_unlocked = is_30_melt and (in_infer_zone or in_full_unlock)
            # 推理区四维评分（仅推理区需要）
            inference_score = 0
            if is_30_melt and in_infer_zone:
                # 昨日情绪评分
                try:
                    _yesterday_up = json.load(open(BASE.parent / 'trading' / '系统状态.json')).get('yesterday', {}).get('up_count', 9999)
                except: _yesterday_up = 9999
                if _yesterday_up < 1500: inference_score += 2
                elif _yesterday_up < 2000: inference_score += 1
                # 修复速度评分（简化：当前up_count vs 昨日）
                if _yesterday_up > 0:
                    _delta = up_count - _yesterday_up
                    if _delta >= 300: inference_score += 2
                    elif _delta >= 200: inference_score += 1
                # 板块强度（涨停家数）
                if emotion and emotion.get('zt', 0) > 50: inference_score += 1
                # 量能确认：暂不评分（无盘中成交额对比数据源）
                # TODO: 接入Level-2逐笔成交额或分钟级K线后补充
            infer_passed = (not is_30_melt) or (realtime_unlocked and inference_score >= 3)
            if item.get('status') == '已买入' or (is_30_melt and not infer_passed):
                continue

            q = quotes[code]

            # 停牌检测（华泰API提供，westock无此字段）
            if q.get('is_suspended'):
                continue

            # 决策网关 stock 级封锁：allow_buy=false 则跳过
            dl_stocks = decision_flags.get('stocks', {})
            if name in dl_stocks and not dl_stocks[name].get('allow_buy', True):
                dl_reason = dl_stocks[name].get('reason', '决策网关锁定')
                print(f"  🛡️  {name}({code}): 决策网关锁定 — {dl_reason}")
                continue

            # 涨停封死→跳过（优先用limitUp判断，更可靠；兜底用pct）
            limit_up = q.get('limit_up', 0)
            if limit_up > 0:
                if q['price'] >= limit_up * 0.999:  # 允许0.1%浮动容差
                    item['status'] = '涨停错过'
                    continue
            elif q['pct'] >= 9.8:
                item['status'] = '涨停错过'
                continue

            reason = None

            if dim == '1.0分歧低吸':
                reason = _check_divergence_low(code, name, quotes, q)
            elif dim == '2.0板块卡位':
                reason = _check_sector_leader(code, name, item, q)
            elif dim == '3.0趋势低吸':
                reason = _check_trend_low(code, name, quotes, q, up_count, item, realtime_unlocked)

            if reason:
                # 极冰点保护
                if extreme_freeze and dim == '1.0分歧低吸':
                    reason = f"[极冰点跳过] {reason}"
                    continue
                # 情绪维度过滤：非主导维度不盘中买入
                # 推理区解锁的3.0绕过维度过滤
                dim_prefix = dim.split('-')[0]
                if not (dim == '3.0趋势低吸' and realtime_unlocked):
                    if dominant_dim not in ('辅助', dim_prefix) and dim_prefix not in dominant_dim.split('+'):
                        continue
                # 动态仓位
                base_pct = BASE_POSITION_PCT.get(dim, 10)
                adj_pct = adjust_position_pct(base_pct, pos_limit, len(positions))
                # 推理区解锁的3.0仓位减半
                if dim == '3.0趋势低吸' and realtime_unlocked and in_infer_zone:
                    adj_pct = adj_pct / 2
                if adj_pct <= 0:
                    continue
                # 分钟K线确认（thsdk集成）：买入信号需突破5分钟前高才触发
                if minute_signals and code in minute_signals:
                    ms = minute_signals[code]
                    has_price_break = any(
                        sig['type'] == 'price_break' for sig in ms.get('signals', [])
                    )
                    if not has_price_break:
                        # 无分钟K线价格突破确认，跳过买入（保留监控）
                        print(f"  ⏸️  {name}({code}): 买点触发但分钟K线未突破前高，跳过")
                        continue
                sector = item.get('sector', item.get('板块', item.get('track', item.get('产业逻辑', ''))))
                # ── 开盘价交叉验证 v1.2: 防幻影价 ──
                open_price = _fetch_open_price_qt(code)
                min_mult = PRICE_GUARD.get('min_multiplier_of_open', 0.95)
                if open_price and open_price > 0 and q['price'] < open_price * min_mult:
                    print(f"⚠️ {name}({code}): 华泰报价{q['price']}低于腾讯开盘价{open_price}的{min_mult*100:.0f}%，疑似幻影价，拒绝买入",
                          file=sys.stderr)
                    continue
                buy(code, name, q['price'], reason, dim, up_count=up_count, position_pct=adj_pct, sector=sector)
                item['status'] = '已买入'
                positions.append(code)  # 记录持仓
                triggers.append((code, name, reason, 'BUY'))
            elif reason is not None and '跌破MA10' in str(reason):
                pass  # 破位移出（不加入新列表）
            else:
                pass  # 保留监控

    return triggers

def _check_divergence_low(code, name, quotes, q):
    """1.0分歧低吸：回踩MA5/MA10 + 缩量"""
    klines = fetch_kline(code, 10)
    if not klines or len(klines) < 5:
        return None
    ma5 = calc_ma(klines, 5)
    ma10 = calc_ma(klines, 10)
    if not ma5 or not ma10:
        return None
    if q['price'] < ma10 * 0.98:
        return f"跌破MA10({ma10:.2f})"
    # 缩量检查
    vol_5avg = sum(k['volume'] for k in klines[-5:]) / 5
    now = datetime.datetime.now()
    elapsed_min = (now.hour - 9) * 60 + now.minute - 25
    if now.hour >= 13:
        elapsed_min = 125 + (now.hour - 13) * 60 + now.minute
    if elapsed_min > 0:
        est_full_vol = q['vol'] / (elapsed_min / 240)
    else:
        est_full_vol = q['vol']
    if est_full_vol > vol_5avg * 1.2:
        return None  # 量能未缩
    if q['pct'] > 3:
        return None  # 涨幅过大
    return f"分歧低吸：回踩MA5({ma5:.2f})/MA10({ma10:.2f})不破 + 缩量({q['vol']:.0f}手→预估{est_full_vol:.0f}手≤均量{vol_5avg:.0f}手)"

def _check_sector_leader(code, name, item, q):
    """2.0板块卡位：板块前排高开"""
    # 简化：竞价未通过的不追高，等下次竞价
    return None

def _check_trend_low(code, name, quotes, q, up_count, item, realtime_unlocked=False):
    """3.0趋势低吸：回踩均线"""
    locked = item.get('locked', False)
    melt_locked = locked and '熔断' in item.get('锁定原因', '')
    # 使用detect_buypoints传入的realtime_unlocked（已按配置计算）
    if melt_locked and not realtime_unlocked:
        return None  # 冰点熔断（盘中未修复）
    klines = fetch_kline(code, 12)
    ma5 = calc_ma(klines, 5)
    if not ma5:
        return None
    if q['price'] < ma5 * 0.98:
        return f"跌破MA5({ma5:.2f})"
    return f"趋势低吸：回踩MA5({ma5:.2f})不破 + 情绪{up_count}（盘中解锁）"

# ==================== 尾盘专项 ====================
def late_session_check(emotion, quotes, positions):
    """14:45+尾盘专项"""
    outputs = []
    if not emotion:
        return outputs

    up = emotion['up']
    if up < 1500: phase = "冰点"
    elif up < 2000: phase = "弱势"
    elif up < 2500: phase = "温和"
    elif up < 3500: phase = "活跃"
    else: phase = "极度高潮"

    outputs.append(f"📍 尾盘定调: {up}涨/{emotion['down']}跌 → {phase}")

    # 情绪减仓提示
    if up < 1500:
        outputs.append("🚨 冰点→建议清仓非1.0持仓")
    elif up > 3500:
        outputs.append("🔴 极度高潮→辅助模式，仓位上限20%")

    # 涨停池快查（via westock-data lhb）
    try:
        r = subprocess.run(
            [_NODE, _WESTOCK_SCRIPT, "lhb"],
            capture_output=True, text=True, timeout=15
        )
        lhb_data = json.loads(r.stdout)
        if isinstance(lhb_data, list) and len(lhb_data) > 0:
            # 从龙虎榜统计板块分布
            sectors = Counter(
                item.get('sector', item.get('industry', '其他'))
                for item in lhb_data
            )
            top3 = sectors.most_common(3)
            outputs.append(f"🔥 龙虎榜: {len(lhb_data)}只 | {' | '.join(f'{s}:{c}只' for s, c in top3)}")
    except:
        pass

    return outputs


def _load_decision_flags_with_fallback():
    """
    加载决策开关，带冰点防御兜底。
    优先读取 decision_flags.json（网关产出）；
    若不存在（时序竞态：巡检早于网关），自行解析最新盘前报告构建决策开关。
    """
    df_path = BASE.parent / 'trading' / 'decision_flags.json'

    # 优先：读取网关产出
    if df_path.exists():
        try:
            with open(df_path) as df:
                flags = json.load(df)
            frozen = flags.get('new_order_frozen', False)
            if frozen:
                print(f"🛡️  决策网关: ❌ 新开仓冻结 — {flags.get('frozen_reason', '')}")
            else:
                print(f"🛡️  决策网关: ✅ 新开仓允许 — 仓位上限{flags.get('position_limit', '正常')}")
            return flags
        except Exception as e:
            print(f"⚠️ 决策网关读取失败({e})，降级至报告解析")

    # 兜底：自行解析最新盘前报告
    print("⚠️ decision_flags.json 不存在，巡检启动早于决策网关 → 自行解析盘前报告兜底")
    report_path = _find_latest_premarket_report()
    if not report_path:
        print("❌ 无法找到盘前报告，不冻结（最大限度确保不遗漏）")
        return {}

    print(f"📄 兜底报告: {report_path}")
    report_info = _parse_premarket_for_patrol(report_path)
    if not report_info:
        return {}

    # 加载风控配置
    try:
        rc_path = BASE.parent / 'config' / 'risk_control.json'
        if rc_path.exists():
            with open(rc_path) as f:
                risk_config = json.load(f)
        else:
            risk_config = {'new_order_frozen_on_ice_point': True}
    except Exception:
        risk_config = {'new_order_frozen_on_ice_point': True}

    flags = _build_decision_flags_from_report(report_info, risk_config)
    frozen = flags.get('new_order_frozen', False)
    if frozen:
        print(f"🛡️  兜底决策: ❌ 新开仓冻结 — {flags.get('frozen_reason', '')}")
    else:
        print(f"🛡️  兜底决策: ✅ 新开仓允许 — 仓位上限{flags.get('position_limit', '正常')}")
    return flags


def _find_latest_premarket_report():
    """定位最新的盘前选股报告（与决策网关同逻辑）"""
    report_dir = BASE.parent / 'reports'
    if not report_dir.exists():
        return None
    candidates = list(report_dir.glob('盘前选股_*.md'))
    if not candidates:
        return None
    candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return candidates[0]


def _parse_premarket_for_patrol(report_path):
    """解析盘前报告，提取上涨家数、仓位建议、标的锁定状态"""
    text = Path(report_path).read_text(encoding='utf-8')
    result = {
        'up_count': 0,
        'position_advice': '正常',
        'is_ice_point': False,
        'ice_reason': '',
        'stocks': {},
    }

    # 提取上涨家数
    m = re.search(r'(\d+)\s*涨.*?(\d+)\s*跌', text)
    if m:
        result['up_count'] = int(m.group(1))

    up = result['up_count']

    # 仓位建议
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

    # 解析3.0趋势低吸节标的锁定状态
    in_30_section = False
    for line in text.split('\n'):
        if '3.0趋势低吸' in line:
            in_30_section = True
            continue
        if '1.0分歧低吸' in line or '1.0一进二' in line or '2.0板块卡位' in line:
            in_30_section = False
            continue
        if not in_30_section:
            continue

        stock_match = re.match(r'.*?(\w[\u4e00-\u9fa5]+?)\((\d{6})\)', line)
        if stock_match:
            name = stock_match.group(1)
            code = stock_match.group(2)
            allow_buy = True
            reason = ''

            if '熔断' in line or 'locked' in line.lower():
                allow_buy = False
                reason = f'冰点·3.0熔断'
            elif '锁定' in line:
                allow_buy = False
                reason = '锁定'
            elif '辅助' in line and '1成' in line:
                allow_buy = False
                reason = '辅助模式·仅MA10低吸'

            result['stocks'][name] = {
                'code': code,
                'status': 'locked' if not allow_buy else 'observe',
                'reason': reason,
                'allow_buy': allow_buy,
            }

    return result


def _build_decision_flags_from_report(report_info, risk_config):
    """从报告解析结果构建 decision_flags 结构"""
    now = datetime.datetime.now()
    up = report_info.get('up_count', 0)
    position_advice = report_info.get('position_advice', '正常')

    # 冻结判定（与决策网关同逻辑）
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

    new_order_frozen = frozen if risk_config.get('new_order_frozen_on_ice_point', True) else False

    # 构建 stocks
    stocks = {}
    for name, info in report_info.get('stocks', {}).items():
        stocks[name] = {
            'code': info.get('code', ''),
            'status': info.get('status', 'observe'),
            'reason': info.get('reason', ''),
            'allow_buy': info.get('allow_buy', True) and not new_order_frozen,
        }

    return {
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
        '_source': 'patrol_fallback',  # 标记来源为兜底解析
    }


# ==================== 主函数 ====================
def run():
    now = datetime.datetime.now()
    now_min = now.hour * 60 + now.minute
    now_hm = now.strftime("%H:%M")
    is_late = now_min >= 14*60+45  # 14:45+

    print(f"{'='*50}")
    print(f"🔍 龙虾盘中巡检 {now_hm}{'（尾盘专项）' if is_late else ''}")
    print(f"{'='*50}")

    # 1. 采集情绪
    emotion = fetch_emotion()
    if emotion:
        up = emotion['up']
        phase = "冰点" if up < 1500 else "弱势" if up < 2000 else "温和" if up < 2500 else "活跃" if up < 3500 else "极度高潮"
        print(f"📡 情绪: {up}涨/{emotion['down']}跌 涨停{emotion['zt']} 跌停{emotion['dt']} → {phase}")
    else:
        print("⚠️ 情绪数据获取失败")
        emotion = {'up': -1, 'down': 0, 'zt': 0, 'dt': 0}

    # 2. 加载持仓 + 候选池，合并所有代码一次获取行情
    pos_data = {}
    try:
        with open(POSITIONS_PATH) as f:
            pos_data = json.load(f)
    except:
        pass

    cand_data = {}
    try:
        with open(CANDIDATES_PATH) as f:
            cand_data = json.load(f)
    except:
        pass

    positions = pos_data.get('positions', [])
    candidates = cand_data.get('candidates', {})

    # 2.1 决策网关：读取当日决策开关（冰点防御闭环）
    # v1.1: 增加兜底解析 — 若 decision_flags.json 不存在（时序竞态），
    # 自行解析最新盘前报告构建临时决策开关，消除巡检与网关之间的竞态窗口。
    decision_flags = _load_decision_flags_with_fallback()

    # 合并所有需要行情的代码
    all_codes = set()
    for p in positions:
        all_codes.add(p['code'])
    for dim in candidates.values():
        for item in dim:
            code = str(item.get('代码', item.get('code', '')))
            if code:
                all_codes.add(code)

    quotes = fetch_quotes(list(all_codes))
    print(f"📊 行情获取: {len(quotes)}只")

    # 2.5 分钟K线信号检查（thsdk集成）
    minute_signals = {}
    try:
        minute_path = BASE.parent / 'trading' / 'minute_signals.json'
        if minute_path.exists():
            with open(minute_path) as mf:
                minute_data = json.load(mf)
            minute_signals = minute_data.get('details', {})
            codes_with_signals = minute_data.get('codes_with_signals', [])
            if codes_with_signals:
                print(f"📡 分钟K线信号: {len(codes_with_signals)}只有异动")
    except Exception as e:
        print(f"⚠️ 分钟K线信号读取失败: {e}")

    # 分钟K线预警（持仓股出现量价异动）
    minute_warnings = []
    for pos in positions:
        code = pos.get('code', '')
        if code in minute_signals:
            ms = minute_signals[code]
            for sig in ms.get('signals', []):
                if sig['type'] == 'volume_spike':
                    minute_warnings.append((code, pos.get('name', ''), f"⚠️ 分钟量异动: {sig['description']}"))
                elif sig['type'] == 'price_break':
                    minute_warnings.append((code, pos.get('name', ''), f"📈 分钟价格突破: {sig['description']}"))
    if minute_warnings:
        print(f"\n🔔 分钟K线预警（{len(minute_warnings)}条）:")
        for code, name, warn in minute_warnings:
            print(f"  {name}({code}): {warn}")

    # 3. 先卖后买
    sell_triggers, stop_statuses = detect_sellpoints(positions, quotes)

    # 决策网关冻结时，直接跳过买入信号
    frozen = decision_flags.get('new_order_frozen', False)
    buy_triggers = []
    if not frozen:
        buy_triggers = detect_buypoints(candidates, quotes, emotion, minute_signals, decision_flags)
    else:
        print(f"⏸️  决策网关冻结新开仓，跳过买入信号扫描")

    # 4. 输出结果
    if sell_triggers:
        print(f"\n🔴 卖点触发 {len(sell_triggers)}只:")
        for code, name, reason, _ in sell_triggers:
            print(f"  {name}({code}): {reason}")

    if buy_triggers:
        print(f"\n🔥 买点触发 {len(buy_triggers)}只:")
        for code, name, reason, _ in buy_triggers:
            print(f"  {name}({code}): {reason}")

    if not sell_triggers and not buy_triggers:
        monitor_count = sum(len(v) for v in candidates.values())
        pos_count = len(positions)
        print(f"\n✅ 无触发 | 监控{monitor_count}只 | 持仓{pos_count}只")

    # 5. 尾盘专项
    if is_late:
        late_out = late_session_check(emotion, quotes, positions)
        if late_out:
            print(f"\n{'─'*40}")
            for line in late_out:
                print(f"  {line}")

    # 6. 持仓状态（含止损状态）
    if positions:
        print(f"\n{'='*70}")
        print(f"📊 持仓监控 | 止损状态")
        print(f"{'─'*70}")
        print(f"{'名称':<10} {'代码':<8} {'现价':<8} {'成本':<8} {'盈亏%':<8} {'止损状态':<16} {'建议操作'}")
        print(f"{'─'*70}")
        for pos in positions:
            code = pos['code']
            name = pos.get('name', '')
            buy_price = float(pos['buy_price'])
            q = quotes.get(code)
            if q and q['price'] > 0:
                pnl = (q['price'] - buy_price) / buy_price * 100
                ss = stop_statuses.get(code, {})
                status = ss.get('status', '正常')
                # 状态图标
                icon_map = {
                    '正常': '✅',
                    '止损预警': '⚠️',
                    '强制止损': '🔴',
                    '移动止盈触发': '📉',
                    '数据缺失': '❓',
                }
                icon = icon_map.get(status, '  ')
                # 建议操作
                if status == '强制止损':
                    advice = f'卖出{q.get("price",0):.2f}'
                elif status == '止损预警':
                    advice = '密切关注'
                elif status == '移动止盈触发':
                    advice = '减仓/清仓'
                else:
                    advice = '持有'
                print(f"{name:<10} {code:<8} {q['price']:<8.2f} {buy_price:<8.2f} {pnl:<+8.1f}% {icon}{status:<14} {advice}")
            else:
                print(f"{name:<10} {code:<8} {'--':<8} {buy_price:<8.2f} {'--':<8} {'❓ 数据缺失':<16} {'--'}")
        print(f"{'='*70}")
    else:
        print(f"\n{trade_status()}")

    # 7. 保存买点通知
    if buy_triggers:
        notify_path = str(BASE.parent / "trading" / f"buy_notification_{datetime.date.today().strftime('%Y%m%d')}.txt")
        with open(notify_path, 'w') as f:
            f.write('\n'.join([f"🔥 {name}({code}): {reason}" for code, name, reason, _ in buy_triggers]))
        print(f"\n✅ 通知已保存: {notify_path}")

    print(f"\n⏱️ 巡检完成 {datetime.datetime.now().strftime('%H:%M:%S')}")

if __name__ == '__main__':
    run()
