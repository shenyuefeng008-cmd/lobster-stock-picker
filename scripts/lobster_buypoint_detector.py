#!/usr/bin/env python3
"""龙虾买点检测器 v1.1 — 检测买点并自动写入模拟交易仓（含开盘时间验证）"""

import json, subprocess, re, sys, datetime, os, os
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent

# ==================== 开盘时间验证 ====================
def is_trading_time():
    """检查当前是否在A股交易时间（含竞价，含收盘后5分钟窗口供复核）"""
    now = datetime.datetime.now()
    hm = now.strftime("%H:%M")
    
    # 竞价阶段 09:15-09:30
    if "09:15" <= hm < "09:30":
        return True
    # 上午交易 09:30-11:30
    if "09:30" <= hm < "11:30":
        return True
    # 下午交易 13:00-15:05
    if "13:00" <= hm <= "15:05":
        return True
    return False

if not is_trading_time():
    print(f"⏸️ 非交易时间 ({datetime.datetime.now().strftime('%H:%M')})，买点监控跳过（正常行为，收盘后可运行）")
    sys.exit(0)

sys.path.insert(0, str(Path(__file__).resolve().parent))
from simulated_trading import buy, status as _status_func

# ==================== 配置加载（C+B：3.0情绪解锁规则） ====================
def load_config():
    """读取lobster-config.json"""
    cfg_path = Path(__file__).resolve().parent.parent / 'lobster-config.json'
    try:
        with open(cfg_path) as f:
            return json.load(f)
    except:
        return {}

def get_30_emotion_rules():
    """获取3.0情绪规则（运行时动态）"""
    cfg = load_config()
    rules = cfg.get('3.0_emotion_rules', {})
    aux_mode = rules.get('辅助_mode', {})
    return {
        'enabled': rules.get('enabled', True),
        'allow_lowsuck': aux_mode.get('allow_lowsuck', True),
        'max_pos_cheng': aux_mode.get('max_position_cheng', 1),
        'only_ma10': aux_mode.get('only_ma10_lowsuck', True),
        'lowsuck_max_pct': aux_mode.get('lowsuck_max_pct', 3),
        'unlock_on_drop_to': rules.get('unlock_on_drop_to', 3500),
        'melt_below': rules.get('melt_below', 2000),
        'full_activate_above': rules.get('full_activate_above', 2500)
    }


def fetch_live_emotion():
    """实时获取涨跌家数（多源保活），拒绝使用过时数据"""
    import sys, os, subprocess, re, json as _json, urllib.request as _ur
    
    # 添加scripts目录到path
    script_dir = os.path.dirname(os.path.abspath(__file__))
    if script_dir not in sys.path:
        sys.path.insert(0, script_dir)
    
    # === 主源：华泰 marketInsight（HTSC skill） ===
    try:
        htsc_config = os.path.expanduser('~/.htsc-skills/config')
        with open(htsc_config) as f:
            for line in f:
                if '=' in line:
                    k, v = line.strip().split('=', 1)
                    if k == 'HT_APIKEY':
                        os.environ['HT_APIKEY'] = v
                        break
        r = subprocess.run([
            'python3', os.path.join(_FIN_ANALYSIS, 'financial_analysis.py'),
            'marketInsight', '--query', '今天A股涨跌家数 上涨家数 下跌家数 涨停家数 跌停家数'
        ], capture_output=True, text=True, timeout=30, cwd=_FIN_ANALYSIS)
        out = r.stdout + r.stderr
        # 正则提取数字：上涨X家、下跌X家、涨停X家、跌停X家
        mu = re.search(r'上涨[：:\s]*(\d+)\s*家', out)
        md = re.search(r'下跌[：:\s]*(\d+)\s*家', out)
        mz = re.search(r'涨停[：:\s]*(\d+)\s*家', out)
        mt = re.search(r'跌停[：:\s]*(\d+)\s*家', out)
        up = int(mu.group(1)) if mu else 0
        down = int(md.group(1)) if md else 0
        zt = int(mz.group(1)) if mz else 0
        dt = int(mt.group(1)) if mt else 0
        if up > 0 and down > 0:
            return {'up': up, 'down': down, 'zt': zt, 'dt': dt, 'src': 'htsc'}
    except Exception as e:
        print(f"华泰marketInsight失败: {e}")
    
    # === 备源1：腾讯接口采样估算 ===
    try:
        from get_market_sentiment import get_sentiment_legacy_format
        sentiment = get_sentiment_legacy_format()
        if sentiment['up'] > 0 or sentiment['down'] > 0:
            return sentiment
    except Exception as e:
        print(f"腾讯接口采样失败: {e}")
    
    # === 备源2：legulegu.com ===
    try:
        import subprocess, re
        r = subprocess.run(["curl","-s","-L","--max-time","10","-A","Mozilla/5.0",
                          "https://legulegu.com/stockdata/market-activity"],
                          capture_output=True, text=True, timeout=12)
        mu = re.search(r'(\d+)家上涨', r.stdout)
        md = re.search(r'(\d+)家下跌', r.stdout)
        mz = re.search(r'(\d+)家涨停', r.stdout)
        mt = re.search(r'(\d+)家跌停', r.stdout)
        up = int(mu.group(1)) if mu else 0
        down = int(md.group(1)) if md else 0
        zt = int(mz.group(1)) if mz else 0
        dt = int(mt.group(1)) if mt else 0
        if up > 0 or down > 0:
            return {'up': up, 'down': down, 'zt': zt, 'dt': dt, 'src': 'legulegu'}
    except:
        pass
    
    # === 备选源：新浪财经全市场分页统计 ===
    try:
        ups = downs = zts = dts = 0
        for pg in [1, 2, 3, 4, 5]:
            u = "https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/Market_Center.getHQNodeData?page=" + str(pg) + "&num=100&sort=code&asc=1&node=hs_a"
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
            return {'up': ups, 'down': downs, 'zt': zts, 'dt': dts, 'src': 'sina', 'sample': ups + downs}
    except:
        pass
    
    return None


# ==================== 赛道快照加载 ====================
def load_hot_sectors():
    """加载盘前引擎产出的当日热点赛道"""
    try:
        with open(ROOT / 'trading' / 'hot_sectors.json') as f:
            snap = json.load(f)
        return set(snap.get('hot_sectors', []))
    except:
        return set()

# ==================== 催化剂否决规则集成 ====================
try:
    from catalyst_scoring import calculate_catalyst_score, get_catalyst_action
    CATALYST_VETO_ENABLED = True
except ImportError:
    CATALYST_VETO_ENABLED = False
    print("  ⚠️ catalyst_scoring模块未找到，跳过催化剂否决", file=sys.stderr)

# 配置
CAPITAL_TOTAL = 1000000  # 总资金100万
POSITION_PCT_MAP = {
    '1.0分歧低吸': 10,  # 单只10%
    '1.0一进二': 10,
    '2.0板块卡位': 10,
    '3.0趋势低吸': 15,  # 趋势票可大一些
}

def get_kline(code, days=10):
    """获取历史K线（腾讯API），返回列表[{date, open, close, high, low, volume}]"""
    prefix = 'sh' if code.startswith('6') else 'sz'
    url = f"https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?_var=kline_dayhfq&param={prefix}{code},day,,,{days},qfq"
    try:
        r = subprocess.run(['curl', '-s', '--max-time', '10', url], capture_output=True, timeout=12)
        txt = r.stdout.decode('utf-8', 'replace')
        # 解析JSON（注意：返回数据可能无分号结尾）
        m = re.search(r'kline_dayhfq=(.*)', txt)
        if not m: return []
        data = json.loads(m.group(1))
        # 注意：前复权返回qfqday，不复权返回day/nofqday
        stock_data = data.get('data', {}).get(f'{prefix}{code}', {})
        klines_raw = stock_data.get('qfqday', stock_data.get('day', stock_data.get('nofqday', [])))
        # 格式: [日期, 开盘, 收盘, 最高, 最低, 成交量(手)]
        result = []
        for k in klines_raw:
            result.append({
                'date': k[0],
                'open': float(k[1]),
                'close': float(k[2]),
                'high': float(k[3]),
                'low': float(k[4]),
                'volume': int(float(k[5])),  # API返回可能带.000
            })
        return result
    except Exception as e:
        print(f"  ⚠️ 获取{code}K线失败: {e}")
        return []

def calc_ma(klines, period):
    """计算MA"""
    if len(klines) < period:
        return None
    return sum(k['close'] for k in klines[-period:]) / period

def detect_10_divergence_low(code, name, sector, quotes, hot_sectors=None):
    """1.0分歧低吸买点检测：回踩MA5/MA10 + 缩量企稳（已修复盘中量换算bug）
    赛道加权：热点赛道的MA10阈值从2%放宽到3%，缩量判定从1.2放宽到1.3"""
    # 赛道加权：热点赛道降低触发门槛
    is_hot = (hot_sectors and sector in hot_sectors) if hot_sectors else False
    ma10_threshold = 0.97 if is_hot else 0.98   # 热点 -3% vs 普通 -2%
    vol_threshold = 1.3 if is_hot else 1.2       # 热点 130% vs 普通 120%
    import datetime as dt2  # 避免与外层dt冲突
    klines = get_kline(code, 10)
    if not klines or len(klines) < 5:
        return None, "K线数据不足"
    
    ma5 = calc_ma(klines, 5)
    ma10 = calc_ma(klines, 10)
    cur_price = quotes.get(code, {}).get('price', 0)
    cur_pct = quotes.get(code, {}).get('pct', 0)
    
    if not ma5 or not ma10:
        return None, "MA计算失败"
    
    # 条件1：价格在MA5和MA10之间或回踩不破
    if cur_price < ma10 * ma10_threshold:  # 跌破MA10超过阈值
        return None, f"价格{cur_price:.2f}跌破MA10({ma10:.2f})[阈值{int((1-ma10_threshold)*100)}%]"
    
    # 条件2：缩量或平量（v2修复：按已交易时长换算预估全天量再对比）
    vol_5avg = sum(k['volume'] for k in klines[-5:]) / 5  # 单位：手
    cur_vol = quotes.get(code, {}).get('vol_wan', 0)     # 单位：手（腾讯p[36]已换算为手）
    
    now = dt2.datetime.now()
    # 盘中（09:30-11:30 / 13:00-15:00）按已交易时长换算全天预估量
    session_ratio = 1.0  # 收盘后=1，全量对比
    
    if 9*60+25 <= now.hour*60+now.minute < 11*60+30:  # 上午盘中
        elapsed = (now.hour - 9) * 60 + now.minute - 25  # 从09:25起算
        session_ratio = elapsed / ((11*60+30) - (9*60+25))  # 上午段占比约49%
    elif 13*60 <= now.hour*60+now.minute < 15*60+5:  # 下午盘中
        am_minutes = (11*60+30) - (9*60+25)  # 125分钟
        elapsed = am_minutes + (now.hour - 13) * 60 + now.minute
        session_ratio = elapsed / 240  # 全天按240分钟算
    # session_ratio=1.0 则为收盘后或非交易时段，直接对比
    
    # 预估全天量 = 实时量 / 已交易占比
    estimated_full_vol = cur_vol / session_ratio if session_ratio > 0.05 else cur_vol
    
    # 放宽20%容错（应对盘中波动），缩量判定：预估全天量 < 均量*1.2
    if estimated_full_vol > vol_5avg * vol_threshold:
        ratio_pct = cur_vol / vol_5avg * 100 if vol_5avg > 0 else 0
        return None, f"量能未缩(实时{cur_vol:.0f}手→预估全天{estimated_full_vol:.0f}手 > 均量{vol_5avg:.0f}手，实时/均量={ratio_pct:.0f}%)"
    
    # 条件3：涨幅不大（避免追高）
    if cur_pct > 3:
        return None, f"涨幅过大({cur_pct:+.2f}%)"
    
    # 买点触发
    reason = f"分歧低吸：回踩MA5({ma5:.2f})/MA10({ma10:.2f})不破 + 缩量({cur_vol:.0f}手→预估全天{estimated_full_vol:.0f}手 ≤ 均量{vol_5avg:.0f}手)"
    return reason, None

def get_sector_limit_up(sector):
    """获取板块涨停家数（实时从akshare获取）"""
    try:
        import akshare as ak
        df = ak.stock_zt_pool_em(date=datetime.date.today().strftime('%Y%m%d'))
        # 统计该板块涨停家数
        count = len(df[df['所属行业'] == sector]) if '所属行业' in df.columns else 0
        return count
    except:
        # 尝试从 trading/ 读取今日数据
        try:
            limit_file = ROOT / 'trading' / f"sector_limit_up_{datetime.date.today().strftime('%Y%m%d')}.json"
            with open(limit_file, "r") as f:
                data = json.load(f)
                return data.get(sector, 0)
        except:
            return 0

def detect_20_sector_leader(code, name, sector, quotes, sector_zt_count=None):
    """2.0板块卡位买点检测：板块涨停≥3 + 个股前排。
    sector_zt_count 直接从候选JSON的 sector_zt 字段读取（引擎已统计），不再调用akshare。"""
    limit_up_count = sector_zt_count if sector_zt_count is not None else 0
    if limit_up_count < 3:
        return None, f"板块{sector}涨停{limit_up_count}家<3"
    
    cur_pct = quotes.get(code, {}).get('pct', 0)
    # 条件：个股涨幅>3%且不是涨停（留空间）
    if cur_pct < 3:
        return None, f"个股涨幅{cur_pct:+.2f}%<3%"
    if cur_pct >= 9.8:
        return None, f"个股已涨停，错过买点"
    
    reason = f"板块卡位：{sector}涨停{limit_up_count}家+个股前排({cur_pct:+.2f}%)"
    return reason, None

def detect_30_trend_low(code, name, sector, quotes, up_count, locked=False, locked_reason='', hot_sectors=None):
    """3.0趋势低吸买点检测（C+B运行时动态）：
    - 冰点<2000: 3.0熔断
    - 辅助模式>3500: 仅MA10低吸，≤1成
    - 2000-3500: 正常MA5回踩
    - >2500连续2日: 完全激活
    赛道过滤：非热点+非锁定标的，需要异常放量（>均量1.5倍）才触发。"""
    _3r = get_30_emotion_rules()
    
    # 熔断条件
    if up_count < _3r['melt_below']:
        return None, f"冰点·涨跌家数{up_count}<{_3r['melt_below']}，3.0熔断"
    
    # 辅助模式：只允许MA10回踩
    if locked and '辅助模式' in locked_reason:
        # 获取MA10
        klines = get_kline(code, 15)
        if not klines or len(klines) < 10:
            return None, "K线数据不足"
        ma10 = calc_ma(klines, 10)
        cur_price = quotes.get(code, {}).get('price', 0)
        if not ma10:
            return None, "MA10计算失败"
        
        low_suck_max = _3r['lowsuck_max_pct']
        if cur_price < ma10 * 0.97:
            return None, f"价格{cur_price:.2f}跌破MA10({ma10:.2f})>3%"
        if cur_price > ma10 * (1 + low_suck_max / 100):
            return None, f"价格{cur_price:.2f}远离MA10({ma10:.2f})>{low_suck_max}%"
        
        # 辅助模式只做低吸，不追涨
        cur_pct = quotes.get(code, {}).get('pct', 0)
        if cur_pct > 3:
            return None, f"辅助模式·涨幅{cur_pct:+.2f}%过大，不做追涨"
        if cur_pct < -7:
            return None, f"辅助模式·跌幅{cur_pct:+.2f}%过大，不做V反"
        
        reason = f"[辅助·低吸]回踩MA10({ma10:.2f})+涨幅{cur_pct:+.2f}%+情绪{up_count}"
        return ('AUX_LOWSUCK', reason), None
    
    # 正常模式：MA5回踩
    # 赛道感知：非热点+非锁定标的，需要量能辅助确认
    is_hot = (hot_sectors and sector in hot_sectors) if hot_sectors else True  # 无赛道数据时不设限
    if not is_hot and not locked:
        # 非热点板块需额外缩量/放量确认
        klines_check = get_kline(code, 10)
        if klines_check and len(klines_check) >= 5:
            vol_5avg = sum(k['volume'] for k in klines_check[-5:]) / 5
            cur_vol = quotes.get(code, {}).get('vol_wan', 0)
            if cur_vol < vol_5avg * 1.5:
                return None, f"非热点板块({sector})量能不足(实时{cur_vol:.0f}手<均量{vol_5avg:.0f}手×1.5)，不触发"

    klines = get_kline(code, 10)
    if not klines or len(klines) < 5:
        return None, "K线数据不足"
    
    ma5 = calc_ma(klines, 5)
    cur_price = quotes.get(code, {}).get('price', 0)
    
    if not ma5:
        return None, "MA5计算失败"
    
    # 条件：回踩MA5不破（价格在MA5的-2%~+5%区间）
    if cur_price < ma5 * 0.98:
        return None, f"价格{cur_price:.2f}跌破MA5({ma5:.2f})"
    
    cur_pct = quotes.get(code, {}).get('pct', 0)
    if cur_pct > 5:
        return None, f"涨幅过大({cur_pct:+.2f}%)"
    
    reason = f"趋势低吸：回踩MA5({ma5:.2f})不破+情绪{up_count}→激活3.0"
    return ('NORMAL', reason), None



def detect_sell_signals(quotes):
    """检测持仓股的卖点信号，返回[{"code","name","action","reason","pnl_pct"}]"""
    from simulated_trading import _load
    data = _load()
    positions = data.get("positions", [])
    signals = []
    
    for p in positions:
        code = p["code"]
        name = p["name"]
        buy_price = p["buy_price"]
        dimension = p.get("dimension", "")
        q = quotes.get(code)
        if not q:
            continue
        
        current_price = q["price"]
        pnl_pct = (current_price - buy_price) / buy_price * 100
        
        # === 止盈判断 ===
        if pnl_pct >= 25:
            signals.append({"code": code, "name": name, "action": "SELL_ALL", "reason": "止盈25%清仓", "pnl_pct": pnl_pct})
            continue
        elif pnl_pct >= 15 and not p.get("profit_taken"):
            signals.append({"code": code, "name": name, "action": "SELL_HALF", "reason": "止盈15%减半仓", "pnl_pct": pnl_pct})
            continue
        
        # === 止损判断 ===
        # 1. 跌幅止损
        if pnl_pct <= -8:
            signals.append({"code": code, "name": name, "action": "SELL_ALL", "reason": "止损-8%清仓", "pnl_pct": pnl_pct})
            continue
        
        # 2. 收盘价<MA10止损（获取K线计算MA10）
        klines = get_kline(code, 15)
        if klines and len(klines) >= 10:
            ma10 = calc_ma(klines, 10)
            if ma10 and current_price < ma10:
                signals.append({"code": code, "name": name, "action": "SELL_ALL", "reason": f"收盘价{current_price:.2f}<MA10({ma10:.2f})止损", "pnl_pct": pnl_pct})
                continue
            
            # 3. 3.0趋势池特殊止损：MA5<MA10 → 趋势破坏强制卖出
            if dimension == "3.0趋势低吸":
                ma5 = calc_ma(klines, 5)
                if ma5 and ma10 and ma5 < ma10:
                    signals.append({"code": code, "name": name, "action": "SELL_ALL", "reason": f"3.0趋势破坏: MA5({ma5:.2f})<MA10({ma10:.2f})", "pnl_pct": pnl_pct})
                    continue
        
        # === 超短卖点：收盘未封板 ===
        # 判断是否涨停（涨幅>=9.8%视为涨停）
        pct = q.get('pct', 0)
        is_limit = pct >= 9.8
        last_close = q.get('last_close', 0)
        # 仅在14:50后检测（14:50=890分钟）
        from datetime import datetime
        now = datetime.now()
        now_min = now.hour * 60 + now.minute
        if now_min >= 890:
            # 超短逻辑：收盘未封板则卖出（不留恋）
            if not is_limit and pnl_pct >= 5:
                signals.append({"code": code, "name": name, "action": "SELL_ALL", "reason": f"超短收盘未封板+盈利{pnl_pct:.1f}%清仓", "pnl_pct": pnl_pct})
    
    return signals

def execute_sell_signals(signals, quotes):
    """执行卖出信号"""
    from simulated_trading import sell, sell_partial
    results = []
    for s in signals:
        code = s["code"]
        action = s["action"]
        
        if action == "SELL_ALL":
            r = sell(code, quotes[code]["price"], "卖点监控自动卖出", s["reason"])
            results.append(f"SELL_ALL {s['name']}: {r}")
        elif action == "SELL_HALF":
            r = sell_partial(code, 50, quotes[code]["price"], "卖点监控自动卖出", "止盈15%减半仓")
            results.append(f"SELL_HALF {s['name']}: {r}")
    
    return results


def check_catalyst_veto(dim, item, quotes):
    """
    催化剂否决规则：返回None表示不否决，返回字符串表示否决原因
    """
    if not CATALYST_VETO_ENABLED:
        return None
    
    # 获取板块名称
    sector = item.get('板块', item.get('sector', ''))
    if not sector:
        return None  # 无板块信息，不否决
    
    # 计算催化剂评分
    result = calculate_catalyst_score(sector)
    grade = result['grade']
    score = result['score']
    
    # 否决规则
    # D级：禁止交易
    if grade == 'D':
        return f"催化剂等级D(总分{score})，禁止交易"
    
    # C级+高热度：降级观察
    if grade == 'C' and result['details']['heat'] >= 4:
        return f"催化剂等级C(总分{score})+高热度，暂观察"
    
    # 返回动作建议
    action = get_catalyst_action(grade)
    if action == 'block':
        return f"催化剂动作=block(总分{score})，禁止交易"
    
    return None  # 不否决



def run():
    """主函数：检测卖点+买点并自动执行"""
    today = datetime.date.today().strftime('%Y-%m-%d')
    
    # ========== 卖点检测（先卖后买）==========
    print("\n" + "="*50)
    print("🛑 卖点检测")
    print("="*50)
    
    # 获取持仓股行情
    from simulated_trading import _load
    data = _load()
    positions = data.get("positions", [])
    
    if positions:
        # 批量获取持仓股实时行情
        codes = [p["code"] for p in positions]
        ql = [f"sh{c}" if c.startswith('6') else f"sz{c}" for c in codes]
        r = subprocess.run(["curl","-s","--max-time","10",f"https://qt.gtimg.cn/q={','.join(ql)}"], capture_output=True, timeout=12)
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
                    quotes[code] = {"price": float(p[4]), "pct": float(p[32])}  # p[4]=当前价, p[3]=昨收
        
        # 检测卖点
        sell_signals = detect_sell_signals(quotes)
        if sell_signals:
            print(f"\n⚠️ 卖点触发 {len(sell_signals)} 只:")
            for s in sell_signals:
                print(f"  {s['name']}({s['code']}) {s['pnl_pct']:+.2f}% → {s['reason']}")
            # 自动执行卖出
            exec_results = execute_sell_signals(sell_signals, quotes)
            for r in exec_results:
                print(f"  {r}")
        else:
            print("  ✅ 无卖点信号")
        
        # 更新positions供后续使用
        positions = _load().get("positions", [])
    else:
        print("  📦 无持仓")
    
    print("\n" + "="*50)
    print("🔥 买点检测")
    print("="*50)
    
    # 读取候选池（全天保持完整，不删除）
    # 优先：关注股JSON（09:25竞价过滤→含全部候选+竞价标注）
    # 降级：盘前候选池JSON（07:00盘前引擎）
    source = '盘前候选池'
    candidates_path = str(ROOT / 'trading' / 'premarket_candidates.json')
    
    watch_path = str(ROOT / 'trading' / 'watchlist_candidates.json')
    if os.path.exists(watch_path):
        try:
            with open(watch_path) as f:
                wd = json.load(f)
            if wd.get('date') == today:
                candidates_path = watch_path
                source = '关注股(竞价过滤+午间更新)'
        except:
            pass
    
    try:
        with open(candidates_path) as f:
            data = json.load(f)
        print(f"✅ 候选来源：{source}")
        print(f"✅ 候选池完整保留，共{sum(len(v) for v in data.get('candidates',{}).values())}只")
    except:
        print("⚠️ 候选池文件不存在")
        return
    
    if data.get('date') != today:
        print("⚠️ 候选池日期非今天")
        return
    
    candidates = data.get('candidates', {})
    emotion = data.get('emotion', {})
    
    # 初始化status字段（如果不存在）
    for dim in candidates:
        for item in candidates[dim]:
            if 'status' not in item:
                item['status'] = '监控中'  # 状态：监控中/涨停错过/已买入/卖点触发
    up_count = emotion.get('涨跌家数', 0)
    # C+B：每次买点扫描都刷新实时情绪（拒绝使用旧数据）
    live_emo = fetch_live_emotion()
    if live_emo and live_emo['up'] > 0:
        up_count = live_emo['up']
        src = live_emo.get('src', '?')
        sample = live_emo.get('sample', '')
        sample_str = f' (样本{sample}只)' if sample else ''
        print(f"  📡 实时情绪: {live_emo['up']}涨/{live_emo['down']}跌 涨停{live_emo['zt']}只{sample_str} [{src}]")
    else:
        # 无实时数据，标记为不可用（禁止使用过时数据做决策）
        print(f"  ⚠️ 所有实时数据源不可用，保持盘前数据({up_count})但标注为过时")
        up_count = -1  # 标记为不可用

    
    # 加载赛道快照
    hot_sectors = load_hot_sectors()
    print(f"  📡 赛道快照: {len(hot_sectors)}个热点赛道{list(hot_sectors)[:5] if hot_sectors else '(空)'}")
    
    # 读取实时行情（从 trading/buypoint_data.json）
    quotes = {}
    try:
        with open(ROOT / 'trading' / 'buypoint_data.json') as f:
            bp_data = json.load(f)
            # 这里需要从步骤1重新获取行情，或者把行情缓存到文件
    except:
        pass
    
    # 重新获取实时行情
    all_codes = []
    for dim in ['1.0一进二', '1.0分歧低吸', '2.0板块卡位', '3.0趋势低吸']:
        for item in candidates.get(dim, []):
            code = str(item.get('代码', item.get('code', '')))
            if code: all_codes.append((code, dim, item))
    
    if not all_codes:
        print("暂无买点触发，候选池为空")
        return
    
    # 批量获取行情
    ql = [f"sh{c}" if c.startswith('6') else f"sz{c}" for c,_,_ in all_codes]
    r = subprocess.run(["curl","-s","--max-time","10",f"https://qt.gtimg.cn/q={','.join(ql)}"], capture_output=True, timeout=12)
    for enc in ["gb2312","gbk","utf-8"]:
        try: txt = r.stdout.decode(enc); break
        except: continue
    else: txt = r.stdout.decode("utf-8","replace")
    
    for line in txt.split(";"):
        m = re.search(r'v_(\w+)="([^"]*)"', line)
        if m:
            p = m.group(2).split("~")
            if len(p) > 37:
                code = p[2]
                quotes[code] = {
                    'price': float(p[4]),  # p[4]=当前价, p[3]=昨收
                    'pct': float(p[32]),
                    'vol_wan': float(p[36]),
                    'amt_wan': float(p[37])
                }
    
    # 逐维度检测买点（涨停/破位删除，其他保留）
    triggers = []
    
    # 1.0分歧低吸（先过滤再检测）
    new_10 = []
    for item in candidates.get('1.0分歧低吸', []):
        code = str(item.get('代码', ''))
        name = item.get('名称', '')
        item_status = item.get('status', '监控中')
        if code not in quotes: 
            new_10.append(item)
            continue
        
        # 如果已买入，跳过买点检测但保留
        if item_status == '已买入':
            print(f"  {name}({code}) 已买入，跳过买点检测")
            new_10.append(item)
            continue
        
        # 检查是否涨停错过（删除）
        cur_pct = quotes.get(code, {}).get('pct', 0)
        if cur_pct >= 9.8:
            print(f"  {name}({code}) 涨停错过，移出候选池")
            continue  # 不加入new_10，即删除
        
        # 检测买点
        sector = item.get('sector', '')
        reason, err = detect_10_divergence_low(code, name, sector, quotes, hot_sectors)
        if reason:
            # 催化剂否决检查（NEW）
            veto = check_catalyst_veto('1.0分歧低吸', item, quotes)
            if veto:
                print(f"  ⚠️ {name}({code}) 催化剂否决: {veto}")
                item['status'] = '催化剂否决'
                new_10.append(item)
                continue
            
            pos_pct = POSITION_PCT_MAP.get('1.0分歧低吸', 10)
            sector = item.get('sector', item.get('track', ''))
            catalyst_grade = item.get('catalyst_grade', '')
            result = buy(code, name, quotes[code]['price'], reason, '1.0分歧低吸', pos_pct, sector=sector, catalyst_grade=catalyst_grade)
            triggers.append(f"🔥 1.0分歧低吸 {name}({code}): {reason}\n   {result}")
            # 更新状态为已买入
            item['status'] = '已买入'
            new_10.append(item)
        else:
            # 检查是否破位（删除）
            if err and '跌破MA10' in err:
                print(f"  {name}({code}) 破位，移出候选池: {err}")
                continue  # 不加入new_10，即删除
            else:
                print(f"  {name}({code}) 未触发: {err}")
                new_10.append(item)  # 保留监控
    candidates['1.0分歧低吸'] = new_10
    
    # 2.0板块卡位（先过滤再检测）
    new_20 = []
    for item in candidates.get('2.0板块卡位', []):
        code = str(item.get('代码', ''))
        name = item.get('名称', '')
        sector = item.get('板块', '')
        item_status = item.get('status', '监控中')
        if code not in quotes: 
            new_20.append(item)
            continue
        
        # 如果已买入，跳过买点检测但保留
        if item_status == '已买入':
            print(f"  {name}({code}) 已买入，跳过买点检测")
            new_20.append(item)
            continue
        
        # 检查是否涨停错过（删除）
        cur_pct = quotes.get(code, {}).get('pct', 0)
        if cur_pct >= 9.8:
            print(f"  {name}({code}) 涨停错过，移出候选池")
            continue  # 不加入new_20，即删除
        
        # 检测买点
        sector_zt_count = item.get('sector_zt', 0)
        reason, err = detect_20_sector_leader(code, name, sector, quotes, sector_zt_count)
        if reason:
            # 催化剂否决检查（NEW）
            veto = check_catalyst_veto('2.0板块卡位', item, quotes)
            if veto:
                print(f"  ⚠️ {name}({code}) 催化剂否决: {veto}")
                item['status'] = '催化剂否决'
                new_20.append(item)
                continue
            
            pos_pct = POSITION_PCT_MAP.get('2.0板块卡位', 10)
            sector = item.get('sector', item.get('track', ''))
            catalyst_grade = item.get('catalyst_grade', '')
            result = buy(code, name, quotes[code]['price'], reason, '2.0板块卡位', pos_pct, sector=sector, catalyst_grade=catalyst_grade)
            triggers.append(f"🔥 2.0板块卡位 {name}({code}): {reason}\n   {result}")
            # 更新状态为已买入
            item['status'] = '已买入'
            new_20.append(item)
        else:
            # 板块卡位没有破位概念，保留监控
            print(f"  {name}({code}) 未触发: {err}")
            new_20.append(item)  # 保留监控
    candidates['2.0板块卡位'] = new_20
    
    # 无实时数据时，跳过所有维度买点（保守操作）
    if up_count == -1:
        print("  ⏸️ 所有数据源不可用，今日暂停买点检测")
        candidates['1.0一进二'] = []
        candidates['1.0分歧低吸'] = []
        candidates['2.0板块卡位'] = []
        candidates['3.0趋势低吸'] = []
        if triggers:
            pass  # 空，不触发任何买点
        else:
            print("  无买点触发（数据不可用）")
        return candidates
    
    # 3.0趋势低吸（先过滤再检测）
    new_30 = []
    for item in candidates.get('3.0趋势低吸', []):
        code = str(item.get('代码', ''))
        name = item.get('名称', '')
        item_status = item.get('status', '监控中')
        if code not in quotes: 
            new_30.append(item)
            continue
        
        # 如果已买入，跳过买点检测但保留
        if item_status == '已买入':
            print(f"  {name}({code}) 已买入，跳过买点检测")
            new_30.append(item)
            continue
        
        # 检查是否涨停错过（删除）
        cur_pct = quotes.get(code, {}).get('pct', 0)
        if cur_pct >= 9.8:
            print(f"  {name}({code}) 涨停错过，移出候选池")
            continue  # 不加入new_30，即删除
        
        # C+B：读取locked状态，冰点熔断跳过，辅助模式可低吸
        locked = item.get('locked', False)
        locked_reason = item.get('锁定原因', '')
        if locked and '熔断' in locked_reason:
            print(f"  {name}({code}) 冰点熔断({locked_reason})")
            new_30.append(item)
            continue
        
        # 检测买点（传入locked状态）
        sector = item.get('sector', '')
        result = detect_30_trend_low(code, name, sector, quotes, up_count, locked, locked_reason, hot_sectors)
        if isinstance(result, tuple) and len(result) == 2:
            reason, err = result
        else:
            reason, err = None, str(result)
        
        if reason:
            # 解包返回类型
            if isinstance(reason, tuple) and len(reason) == 2:
                buy_type, reason_text = reason
            else:
                buy_type, reason_text = 'NORMAL', reason
            
            # 催化剂否决检查
            veto = check_catalyst_veto('3.0趋势低吸', item, quotes)
            if veto:
                print(f"  ⚠️ {name}({code}) 催化剂否决: {veto}")
                item['status'] = '催化剂否决'
                new_30.append(item)
                continue
            
            # C+B：辅助模式仓位上限10%，正常模式按配置
            _3r = get_30_emotion_rules()
            if buy_type == 'AUX_LOWSUCK':
                pos_pct = int(_3r['max_pos_cheng'] * 10)
                dim_label = '3.0辅助低吸'
            else:
                pos_pct = POSITION_PCT_MAP.get('3.0趋势低吸', 15)
                dim_label = '3.0趋势低吸'
            
            sector = item.get('sector', item.get('track', ''))
            catalyst_grade = item.get('catalyst_grade', '')
            result = buy(code, name, quotes[code]['price'], reason_text, dim_label, pos_pct, sector=sector, catalyst_grade=catalyst_grade)
            triggers.append(f"🔥 {dim_label} {name}({code}): {reason_text}\n   仓位{pos_pct}%  {result}")
            item['status'] = '已买入'
            new_30.append(item)
        else:
            if err and ('跌破MA5' in err or '跌破MA10' in err):
                print(f"  {name}({code}) 破位，移出候选池: {err}")
                continue
            else:
                print(f"  {name}({code}) 未触发: {err}")
                new_30.append(item)
    candidates['3.0趋势低吸'] = new_30
    
    # 输出结果 + 保存候选池状态（不删除）
    if triggers:
        print(f"\n📊 买点触发 {len(triggers)} 只:")
        for t in triggers:
            print(t)
        print(f"\n{_status_func()}")
        
        # 保存通知文件供CRON任务AI读取
        notify_lines = [f"买点触发 {len(triggers)} 只:"]
        for t in triggers:
            # 提取核心信息：格式如 "🔥 1.0分歧低吸 中锐股份(002374): 分歧低吸：回踩..."
            if ':' in t:
                core = t.split('\n')[0]  # 第一行
                notify_lines.append(core)
        # 金额状态
        s = _status_func()
        for line in s.split('\n'):
            if '可用' in line or '初始' in line:
                notify_lines.append(line)
                break
        
        notify_path = str(ROOT / 'trading' / f"buy_notification_{datetime.date.today().strftime('%Y%m%d')}.txt")
        with open(notify_path, 'w') as f:
            f.write('\n'.join(notify_lines))
        print(f"\n✅ 通知已保存: {notify_path}")
    else:
        print(f"暂无买点触发，情绪{emotion.get('主导维度', '未知')}，继续观察")
        # 清除旧通知文件
        try:
            os.remove(str(ROOT / 'trading' / f"buy_notification_{datetime.date.today().strftime('%Y%m%d')}.txt"))
        except:
            pass
    
    # ✅ 关键：保存候选池（带状态，不删除任何候选）
    try:
        with open(candidates_path, 'w') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"\n✅ 候选池已保存（含状态），共{sum(len(v) for v in candidates.values())}只")
    except Exception as e:
        print(f"\n⚠️ 候选池保存失败: {e}")

if __name__ == '__main__':
    run()
