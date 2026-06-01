#!/usr/bin/env python3
"""龙虾盘中巡检 v1.0 — 统一买卖点监控（合并原买点/卖点/尾盘3个任务）

调度：
  10:00,10:30,13:00,13:30,14:00,14:30 → 常规巡检
  14:45 → 尾盘专项（加情绪定调+异动扫描）
  14:50 → 超短卖点预警（涨停次日未封板→卖出）

逻辑：一次采集 → 先卖后买 → 统一输出
"""

import json, subprocess, re, sys, datetime, os
from pathlib import Path
from collections import Counter

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
CANDIDATES_PATH = "/tmp/lobster_watchlist_candidates.json"
POSITIONS_PATH = BASE.parent / "trading" / "模拟持仓.json"

STOP_LOSS = {'1.0一进二': -5.0, '1.0分歧低吸': -5.0, '2.0板块卡位': -7.0, '3.0趋势低吸': -3.0}
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
    return tier.get('dim','1.0'), tier.get('pos_limit', 10), tier.get('dim','1.0')

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
                    new_pos = min(pos_limit, 3)  # 极端保守
                corrections.append(f"剧烈波动日(delta={delta}), {dim}→{new_dim}, 仓位{pos_limit}→{new_pos}成")
                dim = new_dim
                pos_limit = new_pos
            except:
                pass
    
    # 校验2：缩量修正（今日成交额<前日，不得升级只能维持或降级）
    if today_volume and yesterday_volume and yesterday_volume > 0:
        if today_volume < yesterday_volume:
            # 如果基础判定已升级（vs昨日），则降回
            corrections.append(f"缩量修正(今{today_volume/1e8:.0f}亿<昨{yesterday_volume/1e8:.0f}亿), 禁止升级")
            # 缩量时仓位上限额外收紧1成
            pos_limit = max(pos_limit - 1, 1)
    
    # 校验3：极端值校验（涨跌家数>4000或<500触发预警）
    if today_up > 4000 or today_up < 500:
        corrections.append(f"⚠️ 极端值预警(涨跌{today_up}), 需人工确认数据有效性")
        # 极端值时保守处理：仓位减半
        pos_limit = max(pos_limit // 2, 1)
    
    return dim, pos_limit, corrections

def adjust_position_pct(base_pct, pos_limit_cheng, used_count):
    """根据情绪矩阵动态调整仓位比例
    
    pos_limit_cheng: 总仓位上限（单位：成，如5表示5成=50%）
    base_pct: 维度基础单仓比例（单位：%，如10表示10%）
    used_count: 当前持仓数量
    
    return: 本次可买单仓比例（单位：%）
    """
    pos_limit_pct = pos_limit_cheng * 10  # 成→%（5成=50%）
    
    # 已持仓数量达到上限
    if used_count >= pos_limit_cheng:
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
    """获取实时涨跌家数（多源保活）"""
    import sys, os
    
    # 添加scripts目录到path
    script_dir = os.path.dirname(os.path.abspath(__file__))
    if script_dir not in sys.path:
        sys.path.insert(0, script_dir)
    
    # === 主源：腾讯接口采样估算 ===
    try:
        from get_market_sentiment import get_sentiment_legacy_format
        sentiment = get_sentiment_legacy_format()
        if sentiment['up'] > 0 or sentiment['down'] > 0:
            return sentiment
    except Exception as e:
        print(f"腾讯接口采样失败: {e}")
    
    # === 备源1：legulegu.com ===
    try:
        import subprocess, re
        r = subprocess.run(["curl","-s","-L","--max-time","10","-A","Mozilla/5.0",
                           "https://legulegu.com/stockdata/market-activity"],
                           capture_output=True, text=True, timeout=12)
        mu = re.search(r'(\d+)家上涨', r.stdout)
        md = re.search(r'(\d+)家下跌', r.stdout)
        mz = re.search(r'(\d+)家涨停', r.stdout)
        mt = re.search(r'(\d+)家跌停', r.stdout)
        if mu and md:
            return {'up': int(mu.group(1)), 'down': int(md.group(1)),
                    'zt': int(mz.group(1)) if mz else 0, 'dt': int(mt.group(1)) if mt else 0}
    except:
        pass
    
    # === 备源2：新浪财经 ===
    try:
        ups = downs = zts = dts = 0
        import urllib.request as _ur
        import json as _json
        for pg in [1, 2, 3]:
            u = f"https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/Market_Center.getHQNodeData?page={pg}&num=100&sort=code&asc=1&node=hs_a"
            req = _ur.Request(u, headers={"User-Agent": "Mozilla/5.0"})
            with _ur.urlopen(req, timeout=8) as resp:
                items = _json.loads(resp.read().decode('gbk'))
            for i in items:
                cp = float(i.get('changepercent', 0))
                if cp > 0: ups += 1
                elif cp < 0: downs += 1
                if cp >= 9.8: zts += 1
                elif cp <= -9.8: dts += 1
            if ups + downs > 100:
                return {'up': ups, 'down': downs, 'zt': zts, 'dt': dts, 'src': 'sina'}
    except:
        pass
    return None

def fetch_quotes(codes):
    """批量获取实时行情 {code: {price, pct, vol, high, low, name}}"""
    if not codes:
        return {}
    ql = [f"sh{c}" if c.startswith('6') else f"sz{c}" for c in codes]
    r = subprocess.run(["curl","-s","--max-time","10",f"https://qt.gtimg.cn/q={','.join(ql)}"],
                      capture_output=True, timeout=12)
    for enc in ["gb2312","gbk","utf-8"]:
        try: txt = r.stdout.decode(enc); break
        except: continue
    else: txt = r.stdout.decode("utf-8","replace")
    quotes = {}
    for line in txt.split(";"):
        m = re.search(r'v_(\w+)="([^"]*)"', line)
        if m:
            p = m.group(2).split("~")
            if len(p) > 37:
                code = p[2]
                quotes[code] = {
                    'price': float(p[3]) if p[3] else 0,
                    'pct': float(p[32]) if len(p) > 32 else 0,
                    'vol': float(p[36]) if len(p) > 36 else 0,
                    'high': float(p[33]) if len(p) > 33 else 0,
                    'low': float(p[34]) if len(p) > 34 else 0,
                    'name': p[1],
                }
    return quotes

def fetch_kline(code, days=10):
    """获取K线数据"""
    prefix = 'sh' if code.startswith('6') else 'sz'
    url = f"https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?_var=kline_dayhfq&param={prefix}{code},day,,,{days},qfq"
    try:
        r = subprocess.run(['curl', '-s', '--max-time', '10', url], capture_output=True, timeout=12)
        m = re.search(r'kline_dayhfq=(.*)', r.stdout.decode('utf-8', 'replace'))
        if not m: return []
        data = json.loads(m.group(1))
        raw = data.get('data', {}).get(f'{prefix}{code}', {})
        klines = raw.get('qfqday', raw.get('day', []))
        return [{'close': float(k[2]), 'volume': int(float(k[5]))} for k in klines]
    except:
        return []

def calc_ma(klines, period):
    if len(klines) < period: return None
    return sum(k['close'] for k in klines[-period:]) / period

# ==================== 卖点检测 ====================
def detect_sellpoints(positions, quotes):
    """检测所有持仓卖点，返回 [(code, name, reason, action)]"""
    triggers = []
    sellable = [p for p in positions if p.get('can_sell')]
    if not sellable:
        return triggers

    for pos in sellable:
        code = pos['code']
        name = pos['name']
        q = quotes.get(code)
        if not q or q['price'] == 0:
            continue
        buy_price = float(pos['buy_price'])
        pnl_pct = (q['price'] - buy_price) / buy_price * 100
        dim = pos.get('dimension', '')
        hold_days = (datetime.date.today() - datetime.datetime.strptime(pos['buy_date'], '%Y-%m-%d').date()).days

        reason = None

        # 1.0/2.0 硬止损
        sl = STOP_LOSS.get(dim, -5.0)
        if pnl_pct <= sl:
            reason = f"{dim}硬止损：回撤{pnl_pct:.2f}% ≤ {sl:.0f}%"

        # 1.0 时间止损
        if not reason and '1.0' in dim and hold_days >= 3 and pnl_pct < 9.8:
            reason = f"1.0时间止损：持仓{hold_days}天未涨停"

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
        if not reason and now_min >= 50 and '1.0' in dim:
            if q['pct'] < 7:
                reason = f"超短卖点：涨停次日未封板(现{q['pct']:.1f}%)"

        # 通用时间止损
        if not reason and hold_days >= MAX_HOLD_DAYS:
            reason = f"时间止损：持仓{hold_days}天 ≥ {MAX_HOLD_DAYS}天"

        if reason:
            sell(code, q['price'], reason, "止损" if "止损" in reason else "止盈")
            triggers.append((code, name, reason, 'SELL'))

    return triggers

# ==================== 买点检测 ====================
def detect_buypoints(candidates, quotes, emotion):
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
    
    print(f"🎮 情绪矩阵: {up_count}涨 → 主导{dominant_dim}, 仓位上限{pos_limit}成")

    # 极冰点保护：<800涨时不做分歧低吸（接飞刀风险极高）
    extreme_freeze = up_count < 800

    for dim in ['1.0分歧低吸', '2.0板块卡位', '3.0趋势低吸']:
        for item in candidates.get(dim, []):
            code = str(item.get('代码', item.get('code', '')))
            name = item.get('名称', item.get('name', ''))
            if not code or code not in quotes:
                continue
            if item.get('status') == '已买入' or item.get('locked') and '熔断' in item.get('锁定原因', ''):
                continue

            q = quotes[code]
            # 涨停错过→移出
            if q['pct'] >= 9.8:
                item['status'] = '涨停错过'
                continue

            reason = None

            if dim == '1.0分歧低吸':
                reason = _check_divergence_low(code, name, quotes, q)
            elif dim == '2.0板块卡位':
                reason = _check_sector_leader(code, name, item, q)
            elif dim == '3.0趋势低吸':
                reason = _check_trend_low(code, name, quotes, q, up_count, item)

            if reason:
                # 极冰点保护
                if extreme_freeze and dim == '1.0分歧低吸':
                    reason = f"[极冰点跳过] {reason}"
                    continue
                # 情绪维度过滤：非主导维度不盘中买入
                dim_prefix = dim.split('-')[0]
                if dominant_dim not in ('辅助', dim_prefix) and dim_prefix not in dominant_dim.split('+'):
                    continue
                # 动态仓位
                base_pct = BASE_POSITION_PCT.get(dim, 10)
                adj_pct = adjust_position_pct(base_pct, pos_limit, len(positions))
                if adj_pct <= 0:
                    continue
                sector = item.get('sector', item.get('板块', item.get('track', item.get('产业逻辑', ''))))
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

def _check_trend_low(code, name, quotes, q, up_count, item):
    """3.0趋势低吸：回踩均线"""
    locked = item.get('locked', False)
    if locked and '熔断' in item.get('锁定原因', ''):
        return None  # 冰点熔断
    klines = fetch_kline(code, 12)
    ma5 = calc_ma(klines, 5)
    if not ma5:
        return None
    if q['price'] < ma5 * 0.98:
        return f"跌破MA5({ma5:.2f})"
    if locked:
        return None  # 等待激活
    if up_count < 2500:
        return None  # 未达到激活条件
    return f"趋势低吸：回踩MA5({ma5:.2f})不破 + 情绪{up_count}"

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
        outputs.append("🔴 极度高潮→辅助模式，仓位上限2成")

    # 涨停池快查
    try:
        import akshare as ak
        today = datetime.date.today().strftime("%Y%m%d")
        df = ak.stock_zt_pool_em(date=today)
        if len(df) > 0:
            sectors = Counter(df.get('所属行业', df.get('板块', [])).tolist())
            top3 = sectors.most_common(3)
            outputs.append(f"🔥 今日涨停: {len(df)}只 | {' | '.join(f'{s}:{c}只' for s, c in top3)}")
    except:
        pass

    return outputs

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

    # 3. 先卖后买
    sell_triggers = detect_sellpoints(positions, quotes)
    buy_triggers = detect_buypoints(candidates, quotes, emotion)

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

    # 6. 持仓状态
    if positions:
        print(f"\n{trade_status()}")

    # 7. 保存买点通知
    if buy_triggers:
        notify_path = f"/tmp/lobster_buy_notification_{datetime.date.today().strftime('%Y%m%d')}.txt"
        with open(notify_path, 'w') as f:
            f.write('\n'.join([f"🔥 {name}({code}): {reason}" for code, name, reason, _ in buy_triggers]))
        print(f"\n✅ 通知已保存: {notify_path}")

    print(f"\n⏱️ 巡检完成 {datetime.datetime.now().strftime('%H:%M:%S')}")

if __name__ == '__main__':
    run()
