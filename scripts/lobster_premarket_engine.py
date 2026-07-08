#!/usr/bin/env python3
"""
龙虾盘前选股引擎 v1.0 — 确定性硬脚本
数据源：legulegu(涨跌家数) + qt.gtimg.cn(指数) + akshare(涨停池/连板池) + 趋势容量池.md(3.0)
输出：trading/premarket_candidates.json + stdout

用法：python3 scripts/lobster_premarket_engine.py
"""

import json, subprocess, re, sys, datetime, os, time
from pathlib import Path

# node 二进制路径（shell executor 的 PATH 不含 /usr/local/bin）
_NODE = '/usr/local/bin/node'
# financial-analysis skill 路径常量（避免四处硬编码）
_FIN_ANALYSIS = os.path.expanduser('~/.qclaw/skills/financial-analysis')

# 确保scripts/目录在sys.path，使catalyst_scoring可被import
SCRIPT_DIR = Path(__file__).parent
ROOT = SCRIPT_DIR.parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

# ==================== 催化剂评分集成 ====================
try:
    from catalyst_scoring import calculate_catalyst_score, get_catalyst_action
    CATALYST_AVAILABLE = True
except ImportError:
    CATALYST_AVAILABLE = False
    print("  ⚠️ catalyst_scoring模块未找到，跳过催化剂评分", file=sys.stderr)

# ==================== 配置（从外部JSON加载，进化任务修改JSON即可） ====================

CONFIG_PATH = Path(__file__).parent.parent / 'lobster-config.json'

# 内置默认值（仅当配置文件不存在时使用）
_DEFAULT_CONFIG = {
    'emotion': {
        'below_1600': {'dim': '1.0', 'aux': '无', 'pos_limit_pct': 30},
        '1600_2000': {'dim': '1.0', 'aux': '无', 'pos_limit_pct': 40},
        '2000_2500': {'dim': '1.0', 'aux': '3.0', 'pos_limit_pct': 90},
        '2500_3500': {'dim': '2.0', 'aux': '1.0', 'pos_limit_pct': 70},
        'above_3500': {'dim': '辅助', 'aux': '无', 'pos_limit_pct': 20},
    }
}

def load_config():
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH) as f:
            cfg = json.load(f)
        print(f"  ✅ 配置文件: lobster-config.json v{cfg.get('_meta',{}).get('version','?')} ({cfg.get('_meta',{}).get('last_updated','?')})")
        return cfg
    else:
        print(f"  ⚠️ 配置文件不存在({CONFIG_PATH})，使用内置默认值")
        return {'emotion': _DEFAULT_CONFIG['emotion']}

EMOTION_RULES = load_config().get('emotion', _DEFAULT_CONFIG['emotion'])

# ==================== 工具函数 ====================

def run(cmd, timeout=20):
    r = subprocess.run(cmd, shell=True, capture_output=True, timeout=timeout)
    try:
        return r.stdout.decode('utf-8').strip()
    except UnicodeDecodeError:
        return r.stdout.decode('gbk', errors='replace').strip()

def get_index():
    raw = run("curl -s 'https://qt.gtimg.cn/q=sh000001,sz399001,sz399006'")
    indices = {}
    for line in raw.split(';'):
        m = re.search(r'v_(\w+)="([^"]*)"', line)
        if m:
            p = m.group(2).split('~')
            if len(p) > 32:
                indices[m.group(1)] = {
                    'name': p[1], 'price': p[3], 'yest': p[4],
                    'change': float(p[32]) if p[32] else 0
                }
    return indices

def get_advance_decline():
    """获取涨跌家数（主动采集+缓存+存档兜底+默认值）"""
    sent_file = ROOT / 'trading' / 'sentiment_cache.json'
    CACHE_TTL = 1800  # 30分钟，与 get_market_sentiment.py 对齐

    # 0. 检查缓存是否有效，无效则主动采集
    cache_fresh = False
    if sent_file.exists():
        try:
            with open(sent_file) as f:
                sent = json.load(f)
            age = time.time() - sent.get('timestamp', 0)
            if age < CACHE_TTL and sent.get('up', 0) > 0:
                cache_fresh = True
        except Exception:
            pass

    if not cache_fresh:
        try:
            print("  🔄 情绪缓存过期/不存在，主动采集...", file=sys.stderr)
            from get_market_sentiment import get_market_sentiment
            get_market_sentiment(use_cache=False)  # 强制采集并写入缓存
        except Exception as e:
            print(f"  ⚠️ 主动采集失败: {e}", file=sys.stderr)

    # 1. 从缓存读取（刚写入或已有效）
    if sent_file.exists():
        try:
            with open(sent_file) as f:
                sent = json.load(f)
            if sent.get('up', 0) > 0:
                print(f"  📡 涨跌家数(实时): {sent['up']}涨/{sent.get('down',0)}跌", file=sys.stderr)
                return {'up': sent['up'], 'down': sent.get('down', 0),
                        'zt': sent.get('zt', 0), 'dt': sent.get('dt', 0)}
        except Exception:
            pass

    # 2. 尝试从系统状态读昨日数据
    state_path = Path(__file__).resolve().parent.parent / "trading" / "系统状态.json"
    if state_path.exists():
        try:
            with open(state_path) as f:
                state = json.load(f)
            yesterday = state.get('yesterday', {})
            if yesterday.get('up_count', 0) > 0:
                print(f"  📡 涨跌家数(系统状态): {yesterday['up_count']}涨/{yesterday.get('down_count',0)}跌", file=sys.stderr)
                return {'up': yesterday['up_count'], 'down': yesterday.get('down_count', 0),
                        'zt': yesterday.get('zt_count', 0), 'dt': yesterday.get('dt_count', 0)}
        except Exception:
            pass

    # 3. 兜底默认值（中性情绪）
    print("  ⚠️ 涨跌家数: 无数据源，使用默认中性值(2500涨/2000跌)", file=sys.stderr)
    return {'up': 2500, 'down': 2000, 'zt': 0, 'dt': 0}

def get_yesterday_date():
    today = datetime.date.today()
    if today.weekday() == 0:  # 周一
        delta = 3
    else:
        delta = 1
    return today - datetime.timedelta(days=delta)

def get_yesterday_zt():
    """昨日涨停池（股票昨天涨停，今天的表现）"""
    yesterday = get_yesterday_date()
    date_str = yesterday.strftime('%Y%m%d')
    
    # ===== 数据源1: westock-data 昨日涨停板块（最稳定）=====
    try:
        westock_script = str(Path(__file__).parent.parent / '.qclaw' / 'skills' / 'westock-data' / 'scripts' / 'index.js')
        if not Path(westock_script).exists():
            westock_script = str(Path.home() / '.qclaw' / 'skills' / 'westock-data' / 'scripts' / 'index.js')
        if Path(westock_script).exists():
            raw = run(f'{_NODE} "{westock_script}" sector pt02031283', timeout=15)
            if raw and '只' in raw:
                # 解析Markdown表格
                zt_list = []
                for line in raw.split('\n'):
                    if line.startswith('|') and ('sh' in line or 'sz' in line or 'bj' in line):
                        parts = [p.strip() for p in line.split('|')]
                        if len(parts) >= 3 and parts[1]:
                            code = parts[1]  # e.g. sh603407
                            name = parts[2]  # e.g. 长裕集团
                            code_pure = code[2:] if len(code) > 2 else code  # 去掉sh/sz前缀
                            # 过滤ST/*ST股
                            if 'ST' in name or 'st' in name.lower():
                                continue
                            zt_list.append({
                                '代码': code_pure,
                                '名称': name,
                                'market_code': code,  # 保留完整代码如sh603407
                                '昨日连板数': 1,  # 板块接口不提供连板数，默认1（首板）
                                '涨停统计': 1,
                                '所属行业': '',  # 后续从行情补充
                                '成交额': 0,
                                '_source': 'westock-sector'
                            })
                if zt_list:
                    print(f"  ✅ 昨日涨停池(westock): {len(zt_list)}只", file=sys.stderr)
                    # 用westock-data批量获取涨跌幅/成交额
                    _enrich_zt_with_quote(zt_list)
                    return zt_list, yesterday.strftime('%Y-%m-%d')
    except Exception as e:
        print(f"  ⚠️ westock-data涨停池失败: {e}", file=sys.stderr)
    
    # ===== 数据源2: akshare（备用）=====
    try:
        raw = run(f"python3 -c \"import akshare as ak, warnings; warnings.filterwarnings('ignore'); df=ak.stock_zt_pool_previous_em(date='{date_str}'); print(df.to_json(orient='records',force_ascii=False))\"")
        if raw:
            result = json.loads(raw)
            if result:
                print(f"  ✅ 昨日涨停池(akshare): {len(result)}只", file=sys.stderr)
                return result, yesterday.strftime('%Y-%m-%d')
            else:
                print(f"  ⚠️ akshare涨停池返回空", file=sys.stderr)
    except Exception as e:
        print(f"  ⚠️ akshare涨停池获取失败: {e}", file=sys.stderr)
    
    print(f"  ❌ 所有涨停池数据源均失败！", file=sys.stderr)
    return [], yesterday.strftime('%Y-%m-%d')

def _enrich_zt_with_quote(zt_list):
    """用westock-data K线获取涨停股的涨跌幅/成交额"""
    # 策略：只enrich连板股（2板以上），首板跳过（量太大）
    # 连板数通过连板池交叉推断，不依赖K线
    try:
        westock_script = str(Path(__file__).parent.parent / '.qclaw' / 'skills' / 'westock-data' / 'scripts' / 'index.js')
        if not Path(westock_script).exists():
            westock_script = str(Path.home() / '.qclaw' / 'skills' / 'westock-data' / 'scripts' / 'index.js')
        
        # 只enrich连板>=2的股票（从连板池来）
        to_enrich = [s for s in zt_list if s.get('昨日连板数', 1) >= 2]
        enriched = 0
        for s in to_enrich[:20]:  # 最多enrich前20只连板股
            mc = s.get('market_code', '')
            if not mc:
                continue
            try:
                raw = run(f'{_NODE} "{westock_script}" kline {mc} --period day --limit 3', timeout=8)
                if not raw:
                    continue
                lines = [l for l in raw.split('\n') if l.startswith('|') and 'date' not in l and '---' not in l]
                if len(lines) >= 2:
                    parts = [p.strip() for p in lines[-2].split('|')]
                    if len(parts) >= 8:
                        try:
                            s['成交额'] = float(parts[8])
                            enriched += 1
                        except:
                            pass
            except:
                continue
        if enriched > 0:
            print(f"  ✅ 连板股K线补充: {enriched}/{len(to_enrich)}只", file=sys.stderr)
    except Exception as e:
        print(f"  ⚠️ 涨停股行情补充失败: {e}", file=sys.stderr)


def fetch_hot_sectors():
    """从华泰 marketInsight 获取昨日板块涨幅TOP10，作为动态赛道快照。内置缓存避免重复调用。"""
    if hasattr(fetch_hot_sectors, '_cache'):
        return fetch_hot_sectors._cache
    import os
    hot_sectors = []
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
            'python3', os.path.expanduser('~/.qclaw/skills/financial-analysis/financial_analysis.py'),
            'marketInsight', '--query', '昨天A股行业板块涨幅排名 TOP10 板块名称'
        ], capture_output=True, text=True, timeout=30,
           cwd=os.path.expanduser('~/.qclaw/skills/financial-analysis'))
        out = r.stdout + r.stderr
        # 先尝试解析 JSON 提取 answer 字段（华泰 API 返回 JSON 格式）
        import re
        hot_sectors = []
        try:
            data = json.loads(r.stdout)
            answer = data.get('data', {}).get('answer', '')
            if answer:
                # answer 格式: "1. 煤炭涨跌幅为3.05%；\n2. 船舶制造涨跌幅为2.69%；..."
                found = re.findall(r'\d+[.、]\s*([^\d\s]+?)涨跌幅', answer)
                hot_sectors = [f.strip() for f in found if len(f.strip()) >= 2]
        except (json.JSONDecodeError, KeyError):
            # JSON 解析失败，回退到原始正则扫描
            pass
        if not hot_sectors:
            # 兜底：原始关键字正则（兼容旧格式 "煤炭板块 +3.05%"）
            found = re.findall(r'\d+[.、]\s*([^\s]+(?:板块|行业|制造|医药|科技|汽车|光伏|储能|军工|半导体|消费|地产|金融|电力|有色|化工|钢铁|煤炭|农业|环保|通信|计算机|传媒|教育|旅游|物流|纺织|服装|家电|食品|饮料|白酒|医疗器械|医疗服务|生物制品|中药|化学制药|创新药|CXO|机器人|AI|人工智能|数字经济|信创|元宇宙|数据要素|算力|芯片|电子|光学|光电子|元件|PCB|面板|软件|游戏|影视|动漫|出版|教育|交通运输|建筑|建材|水泥|玻璃|家居|造纸|包装|零售|贸易|餐饮|酒店|航空|机场|港口|公路|铁路|船舶|航天|军工电子|核电|风电|水电|火电|电网|充电桩|锂电|钠电|固态电池|储能|氢能|光伏组件|逆变器|有机硅|稀土|磁材|钨|钼|铜|铝|黄金|白银|油气|天然气|航运|造船|重工|机械|机床|机器人零部件|传感器|减速器|伺服|PLC|工控|自动化|检测|仪器|仪表|科学仪器|3D打印|新材料|碳纤维|钛合金|高温合金|特钢|不锈钢|有色冶炼|加工|压铸|模具|紧固件|轴承|齿轮|弹簧|阀门|泵|压缩机|风机|电机|变压器|开关|电缆|光纤|光缆|通信模组|天线|滤波器|连接器|射频|基带|芯片设计|晶圆|封测|EDA|IP|光刻|刻蚀|薄膜|清洗|检测设备|零部件|材料|特种气体|光刻胶|抛光|靶材))', out)
            hot_sectors = [f[0] for f in found] if found else []
        print(f"  📡 华泰板块涨幅TOP10: {hot_sectors[:10]}", file=sys.stderr)
    except Exception as e:
        print(f"  ⚠️ 华泰板块涨幅获取失败: {e}", file=sys.stderr)
        hot_sectors = []
    
    # 兜底：如果华泰失败，用 westock-data 获取申万二级行业涨幅排行
    if not hot_sectors:
        try:
            westock_script = str(Path(__file__).parent.parent / '.qclaw' / 'skills' / 'westock-data' / 'scripts' / 'index.js')
            if not Path(westock_script).exists():
                westock_script = str(Path.home() / '.qclaw' / 'skills' / 'westock-data' / 'scripts' / 'index.js')
            raw = run(f'{_NODE} "{westock_script}" sector --rank interval_chg_rank_sw2', timeout=15)
            if raw:
                # 格式: | 1 | pt01801044 | 普钢 | 1.52 | ... → 提取第3列板块名称
                import re
                found = re.findall(r'\|\s*\d+\s*\|[^|]+\|\s*([^|]+?)\s*\|', raw)
                hot_sectors = [f.strip() for f in found if len(f.strip()) >= 2 and not f.strip().isdigit()][:10]
        except:
            pass
    
    # 导出快照供 buyoint_detector 使用
    try:
        snap = {'timestamp': datetime.datetime.now().isoformat(), 'hot_sectors': hot_sectors[:10]}
        hot_path = ROOT / 'trading' / 'hot_sectors.json'
        with open(hot_path, 'w') as f:
            json.dump(snap, f, ensure_ascii=False)
        print(f"  ✅ 赛道快照已写入 {hot_path}", file=sys.stderr)
    except:
        pass
    
    fetch_hot_sectors._cache = hot_sectors
    return hot_sectors


def _enrich_zt_sector(zt_list):
    """用westock-data申万行业成分股反向匹配，给涨停池补所属行业。动态合并华泰热点赛道。"""
    hot_sectors = fetch_hot_sectors()  # 获取当日热点赛道
    try:
        westock_script = str(Path(__file__).parent.parent / '.qclaw' / 'skills' / 'westock-data' / 'scripts' / 'index.js')
        if not Path(westock_script).exists():
            westock_script = str(Path.home() / '.qclaw' / 'skills' / 'westock-data' / 'scripts' / 'index.js')
        
        # 涨停池代码集合
        zt_codes = set()
        for s in zt_list:
            mc = s.get('market_code', '')
            if mc:
                zt_codes.add(mc)
        
        # 核心赛道：config静态 + 华泰动态热点合并
        cfg = load_config()
        static_sectors = cfg.get('track_sectors', ['半导体', '元件', '电力', '化学制品', '有色金属', '汽车零部件', '军工', '光学光电', '通信设备', '电网设备', '计算机', '消费电子', '医疗器械', '光伏', '储能'])
        # 动态热点优先，去重合并
        all_sectors = list(dict.fromkeys(hot_sectors + static_sectors))  # 保持顺序+去重
        hot_set = set(hot_sectors)  # 用于标记 hot_sector
        
        # 逐个赛道搜索申万二级行业，获取成分股，交叉匹配
        code_to_sector = {}
        code_hot = set()  # 属于热点赛道的代码
        for sector_name in all_sectors[:25]:  # 限制25个避免超时
            try:
                # 搜索板块获取代码
                raw = run(f'{_NODE} "{westock_script}" sector --search "{sector_name}"', timeout=8)
                if not raw:
                    continue
                # 找申万二级行业代码
                import re
                for line in raw.split('\n'):
                    if '申万二级' in line and sector_name in line:
                        m = re.search(r'\|\s*(pt\d+)\s*\|', line)
                        if m:
                            sector_code = m.group(1)
                            # 获取成分股
                            raw2 = run(f'{_NODE} "{westock_script}" sector {sector_code}', timeout=12)
                            if raw2:
                                for sline in raw2.split('\n'):
                                    if sline.startswith('|') and ('sh' in sline or 'sz' in sline):
                                        sparts = [p.strip() for p in sline.split('|')]
                                        if len(sparts) >= 2 and sparts[1]:
                                            code_to_sector[sparts[1]] = sector_name
                                            if sector_name in hot_set:
                                                code_hot.add(sparts[1])
                            break
            except:
                continue
        
        # 更新涨停池的所属行业 + 热点标记
        matched = 0
        for s in zt_list:
            mc = s.get('market_code', '')
            if mc in code_to_sector:
                s['所属行业'] = code_to_sector[mc]
                s['hot_sector'] = mc in code_hot
                matched += 1
            elif not s.get('所属行业'):
                s['所属行业'] = '其他'
                s['hot_sector'] = False
        
        print(f"  ✅ 行业匹配: {matched}/{len(zt_list)}只命中赛道（热点赛道{len(hot_sectors)}个）", file=sys.stderr)
    except Exception as e:
        print(f"  ⚠️ 行业匹配失败: {e}", file=sys.stderr)


def get_zt_sub():
    """连板股池 — 从涨停池数据推断连板（>=2板）"""
    yesterday = get_yesterday_date()
    date_str = yesterday.strftime('%Y%m%d')
    
    # ===== 数据源1: westock-data 连板概念板块 =====
    try:
        westock_script = str(Path(__file__).parent.parent / '.qclaw' / 'skills' / 'westock-data' / 'scripts' / 'index.js')
        if not Path(westock_script).exists():
            westock_script = str(Path.home() / '.qclaw' / 'skills' / 'westock-data' / 'scripts' / 'index.js')
        # 搜索连板相关板块
        raw = run(f'{_NODE} "{westock_script}" sector --search 连板', timeout=10)
        if raw and '连板' in raw:
            # 提取连板板块代码
            import re as _re
            m = _re.search(r'\|\s*(pt\d+)\s*\|\s*[^|]*连板', raw)
            if m:
                board_code = m.group(1)
                raw2 = run(f'{_NODE} "{westock_script}" sector {board_code}', timeout=15)
                if raw2 and '只' in raw2:
                    sub_list = []
                    for line in raw2.split('\n'):
                        if line.startswith('|') and ('sh' in line or 'sz' in line):
                            parts = [p.strip() for p in line.split('|')]
                            if len(parts) >= 3 and parts[1]:
                                name = parts[2]
                                if 'ST' in name or 'st' in name.lower():
                                    continue
                                sub_list.append({
                                    '代码': parts[1][2:] if len(parts[1]) > 2 else parts[1],
                                    '名称': parts[2],
                                    '连板数': 2,  # 最少2板
                                    '_source': 'westock-sub'
                                })
                    if sub_list:
                        print(f"  ✅ 连板池(westock): {len(sub_list)}只", file=sys.stderr)
                        return sub_list
    except Exception as e:
        print(f"  ⚠️ westock连板池失败: {e}", file=sys.stderr)
    
    # ===== 数据源2: akshare（备用）=====
    try:
        raw = run(f"python3 -c \"import akshare as ak, warnings; warnings.filterwarnings('ignore'); df=ak.stock_zt_pool_sub_new_em(date='{date_str}'); print(df.to_json(orient='records',force_ascii=False))\"")
        if raw:
            result = json.loads(raw)
            if result:
                print(f"  ✅ 连板池(akshare): {len(result)}只", file=sys.stderr)
                return result
    except Exception as e:
        print(f"  ⚠️ akshare连板池失败: {e}", file=sys.stderr)
    
    # ===== 数据源3: 从涨停池中搜索新闻提取连板信息 =====
    # 从已获取的涨停池中，通过涨幅推断连板（涨幅>10%可能是创业板2板以上）
    print(f"  ⚠️ 所有连板池数据源失败，从涨停池推断", file=sys.stderr)
    return []


def check_pool_staleness(pool_path=None, max_stale_days=3):
    """检查趋势池是否过期（超过3个交易日未更新），返回True则告警"""
    if pool_path is None:
        pool_path = Path(__file__).parent.parent / 'trading' / '趋势容量池.md'
    if not pool_path.exists():
        print(f"  ⚠️ 趋势容量池文件不存在，跳过过期检查", file=sys.stderr)
        return False
    try:
        # 解析"最后更新：YYYY-MM-DD"
        text = pool_path.read_text()
        m = re.search(r'最后更新：(\d{4})-(\d{2})-(\d{2})', text)
        if not m:
            print(f"  ⚠️ 趋势容量池无法解析更新日期，跳过过期检查", file=sys.stderr)
            return False
        last_date = datetime.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        today = datetime.date.today()
        # 数交易日天数（排除周末）
        count = 0
        d = last_date + datetime.timedelta(days=1)
        while d <= today:
            if d.weekday() < 5:  # is_trading_day
                count += 1
            d += datetime.timedelta(days=1)
        if count > max_stale_days:
            print(f"  🔴 警告：趋势池已过期！最后更新{last_date}，距今{count}个交易日未更新（>={max_stale_days+1}个交易日）", file=sys.stderr)
            return True
        else:
            print(f"  ✅ 趋势池最新（最后更新{last_date}，距今{count}个交易日）")
            return False
    except Exception as e:
        print(f"  ⚠️ 趋势池过期检查失败: {e}", file=sys.stderr)
        return False


def get_trend_pool():
    """从趋势容量池.md解析标的"""
    pool_path = Path("/Users/yuefengshen/.qclaw/workspace-1gwpiwf3hr163jz5/trading/趋势容量池.md")
    stocks = []
    if not pool_path.exists():
        return stocks
    in_pool = False
    for line in pool_path.read_text().split('\n'):
        if '当前池中' in line:
            in_pool = True
            continue
        if in_pool and line.startswith('|') and '代码' not in line and '---' not in line and '标的' not in line:
            parts = [p.strip() for p in line.split('|')]
            # v2.1表结构: 标的|代码|赛道|赛道状态|MA5|MA10|MA20|5日均额(亿)|总市值(亿)|总分|入池理由
            if len(parts) >= 11 and parts[1] and parts[2]:
                stocks.append({
                    'name': parts[1], 'code': parts[2],
                    'track': parts[3],
                    'status': parts[4],  # 🔴/🟡/🟢 赛道状态
                    'ma': parts[6],       # MA10（均线参考值）
                    'close': parts[7],    # MA20
                    'amount': parts[8],   # 5日均额(亿)
                    'market_cap': parts[9], # 总市值(亿)
                    'note': parts[11] if len(parts) > 11 else ''
                })
        if in_pool and line.startswith('##'):
            break
    return stocks

def determine_emotion(ad):
    up = ad['up']
    if up < 1600:
        return EMOTION_RULES['below_1600']
    elif up < 2000:
        return EMOTION_RULES['1600_2000']
    elif up < 2500:
        return EMOTION_RULES['2000_2500']
    elif up < 3500:
        return EMOTION_RULES['2500_3500']
    else:
        return EMOTION_RULES['above_3500']

def emotion_triple_check_premarket(emotion, yesterday_up):
    """盘前情绪三重校验（v2.5规则）"""
    today_up = emotion.get('up_count', 0)
    corrections = []
    
    # 校验1：剧烈波动日
    if yesterday_up and yesterday_up > 0:
        delta = abs(today_up - yesterday_up)
        if delta > 1600:
            corrections.append(f"剧烈波动日(delta={delta})")
            # 降级：修改emotion的dim和pos_limit_pct
            dim = emotion.get('dim', '1.0')
            if '2.0' in dim:
                emotion['dim'] = '1.0'
                emotion['pos_limit_pct'] = min(emotion.get('pos_limit_pct', 50), 50)
            elif '3.0' in dim:
                emotion['dim'] = '1.0'
                emotion['pos_limit_pct'] = min(emotion.get('pos_limit_pct', 50), 50)
    
    # 校验2：缩量修正（盘前无成交额数据，跳过）
    
    # 校验3：极端值（仅处理真正的数据错误：>4000高位异常，正常涨跌范围0-4000内不触发）
    # 【BUGFIX 2026-07-01】移除 today_up < 500 条件——139涨是合法冰点数据，不应触发减半
    if today_up > 4000:
        corrections.append(f"极端值预警(涨跌{today_up})")
        emotion['pos_limit_pct'] = max(emotion.get('pos_limit_pct', 50) // 2, 10)
    
    if corrections:
        print(f"🔧 情绪三重校验: {'; '.join(corrections)}")
    return emotion

# ==================== 四维度选股 ====================

def select_10_first_to_second(yesterday_zt):
    """
    1.0一进二：从昨日涨停池筛首板（昨日连板数=1）
    排序：成交额越小越好（<8000万优先），板块涨停数越多越好
    """
    # 筛首板：昨日连板数=1
    first_boards = []
    for s in yesterday_zt:
        lb = s.get('昨日连板数', 0)
        try:
            lb = int(lb)
        except:
            lb = 0
        if lb != 1:
            continue
        
        name = s.get('名称', '')
        code = str(s.get('代码', ''))
        sector = s.get('所属行业', '')
        amount = s.get('成交额', 0)
        try:
            amount = float(amount)
        except:
            amount = 0
        
        amount_yi = amount / 1e8  # 转亿
        
        # 排除一字板（涨跌幅看不出来，但成交额极小的是）
        # 盘前成交额可能为0（westock-data不返回历史成交额），此时不过滤
        if amount_yi > 0 and amount_yi < 0.1:
            continue
        
        first_boards.append({
            'name': name, 'code': code, 'sector': sector,
            'amount': amount_yi, 'amount_raw': amount,
            'hot_sector': s.get('hot_sector', False)
        })
    
    # 统计每个板块有多少只首板（板块强度）
    sector_count = {}
    for s in first_boards:
        sec = s['sector']
        sector_count[sec] = sector_count.get(sec, 0) + 1
    
    # 打分排序
    for s in first_boards:
        score = 0
        score_detail = {}
        # 额区间评分（适配实际首板额1-60亿）
        # 小盘股换手充分+资金效率高 → 适中额高分
        amt = s['amount']
        if 1.0 <= amt <= 3.0:
            as_ = 25       # 最佳区间：小盘换手好
        elif 3.0 < amt <= 8.0:
            as_ = 20       # 中盘：活跃度好
        elif 8.0 < amt <= 20.0:
            as_ = 15       # 中大盘
        elif 0.5 < amt < 1.0:
            as_ = 10       # 微盘
        elif amt > 20.0:
            as_ = 5        # 大盘：资金分散
        else:
            as_ = 0        # 极小盘
        score += as_
        score_detail['额得分'] = as_
        # 板块有其他首板助攻
        sc = sector_count.get(s['sector'], 0)
        _ss = load_config().get('1.0_first_to_second', {}).get('score_sector', {})
        if sc >= 3:
            ss_ = _ss.get('ge_3', 15)
            score += 15
        elif sc >= 2:
            ss_ = _ss.get('ge_2', 10)
            score += 10
        elif sc >= 1:
            ss_ = _ss.get('ge_1', 5)
            score += 5
        else:
            ss_ = 0
        score_detail['板块强度得分'] = ss_
        # 竞价量比得分（封单强度代理）
        zb = s.get('竞价量比', 0)
        if zb >= 10:
            zr_ = 20
        elif zb >= 5:
            zr_ = 15
        elif zb >= 3:
            zr_ = 10
        elif zb >= 1.5:
            zr_ = 5
        else:
            zr_ = 0
        score += zr_
        score_detail['竞价量比得分'] = zr_

        # 封单强度得分（首板封单额 / 总额比）
        if s.get('封单额', 0) > 0 and s['amount'] > 0:
            seal_ratio = s.get('封单额', 0) / s['amount']
            if seal_ratio >= 0.5:
                sr_ = 15
            elif seal_ratio >= 0.3:
                sr_ = 10
            elif seal_ratio >= 0.1:
                sr_ = 5
            else:
                sr_ = 0
        else:
            sr_ = 0
        score += sr_
        score_detail['封单强度得分'] = sr_

        s['score'] = score
        s['score_detail'] = score_detail

    # 催化剂评分（NEW）
    if CATALYST_AVAILABLE:
        for s in first_boards:
            result = calculate_catalyst_score(s['sector'])
            s['catalyst_score'] = result['score']
            s['catalyst_grade'] = result['grade']
            s['catalyst_action'] = get_catalyst_action(result['grade'])
            # 催化剂分数加入总分
            cat_score_map = {'S': 15, 'A': 12, 'B': 8, 'C': 3, 'D': 0}
            cs_add = cat_score_map.get(result['grade'], 0)
            s['score'] = s.get('score', 0) + cs_add
            s['score_detail']['催化剂加分'] = cs_add
        # 按催化剂评分重新排序（S>A>B>C>D）
        grade_order = {'S': 0, 'A': 1, 'B': 2, 'C': 3, 'D': 4}
        first_boards.sort(key=lambda x: (grade_order.get(x.get('catalyst_grade', 'D'), 4), -x['score'], x['amount']))
    
    else:
        # 无催化剂评分，按原评分排序
        first_boards.sort(key=lambda x: (-x['score'], x['amount']))
    return first_boards[:5]

def select_10_divergence(zt_sub, yesterday_zt):
    """
    1.0分歧低吸：2-3连板股，排除≥4板
    从连板池+昨日涨停池的连板数筛选
    """
    candidates = []
    
    # 从昨日涨停池筛2-3板
    for s in yesterday_zt:
        lb = s.get('昨日连板数', 0)
        try:
            lb = int(lb)
        except:
            lb = 0
        _div_cfg = load_config().get('1.0_divergence', {})
        _min_lb = _div_cfg.get('min_lb', 2)
        _max_lb = _div_cfg.get('max_lb', 3)
        if lb < _min_lb or lb > _max_lb:
            continue
        
        name = s.get('名称', '')
        code = str(s.get('代码', ''))
        sector = s.get('所属行业', '')
        amount = s.get('成交额', 0)
        try:
            amount = float(amount)
        except:
            amount = 0
        
        candidates.append({
            'name': name, 'code': code, 'lb': lb,
            'sector': sector, 'amount': amount / 1e8,
            'hot_sector': s.get('hot_sector', False),
            'score': lb * 15,
            'score_detail': {'连板得分': lb * 15, '板块强度得分': 0}
        })
    
    # 按连板数×板块强度排序
    sector_count = {}
    for s in candidates:
        sec = s['sector']
        sector_count[sec] = sector_count.get(sec, 0) + 1
    for s in candidates:
        sc = sector_count.get(s['sector'], 0)
        if sc >= 2:
            s['score'] += 10
            s['score_detail']['板块强度得分'] = 10
    
    # 催化剂评分（NEW）
    if CATALYST_AVAILABLE:
        for s in candidates:
            result = calculate_catalyst_score(s['sector'])
            s['catalyst_score'] = result['score']
            s['catalyst_grade'] = result['grade']
            s['catalyst_action'] = get_catalyst_action(result['grade'])
        # 按催化剂等级排序
        grade_order = {'S': 0, 'A': 1, 'B': 2, 'C': 3, 'D': 4}
        candidates.sort(key=lambda x: (grade_order.get(x.get('catalyst_grade', 'D'), 4), -x['score'], -x['lb']))
    
    else:
        # 无催化剂评分，按原评分排序
        candidates.sort(key=lambda x: (-x['score'], -x['lb']))
    return candidates[:4]

def select_20_sector(yesterday_zt):
    """
    2.0板块卡位：从昨日涨停池按板块统计涨停数，≥3家的板块取前排
    前排 = 成交额最大的（资金认可度高）
    """
    sector_count = {}
    sector_stocks = {}
    
    for s in yesterday_zt:
        sector = s.get('所属行业', '')
        if not sector or sector == '其他':
            continue
        sector_count[sector] = sector_count.get(sector, 0) + 1
        if sector not in sector_stocks:
            sector_stocks[sector] = []
        
        name = s.get('名称', '')
        code = str(s.get('代码', ''))
        amount = s.get('成交额', 0)
        try:
            amount = float(amount)
        except:
            amount = 0
        
        sector_stocks[sector].append({
            'name': name, 'code': code, 'amount': amount / 1e8,
            'amount_raw': amount
        })
    
    # 板块≥3家涨停
    valid_sectors = sorted(
        {k: v for k, v in sector_count.items() if v >= 3}.items(),
        key=lambda x: -x[1]
    )
    
    candidates = []
    for sector, count in valid_sectors:
        stocks = sector_stocks.get(sector, [])
        stocks.sort(key=lambda x: x['amount_raw'], reverse=True)
        for s in stocks[:2]:
            s['sector'] = sector
            s['sector_zt'] = count
            s['score'] = count * 12 + min(s['amount'], 30)
            s['score_detail'] = {'板块涨停得分': count * 12, '成交额得分': min(s['amount'], 30)}
            
            # 催化剂评分（NEW）
            if CATALYST_AVAILABLE:
                result = calculate_catalyst_score(sector)
                s['catalyst_score'] = result['score']
                s['catalyst_grade'] = result['grade']
                s['catalyst_action'] = get_catalyst_action(result['grade'])
            
            candidates.append(s)
    
    # 按催化剂等级排序（S>A>B>C>D），同级按原评分
    if CATALYST_AVAILABLE:
        grade_order = {'S': 0, 'A': 1, 'B': 2, 'C': 3, 'D': 4}
        candidates.sort(key=lambda x: (grade_order.get(x.get('catalyst_grade', 'D'), 4), -x['score']))
    else:
        candidates.sort(key=lambda x: x['score'], reverse=True)
    
    return candidates[:5]

def select_30_trend(trend_pool, emotion):
    """3.0趋势低吸：从趋势容量池选（C+B：辅助模式也生成候选，运行时动态解锁）"""
    today_up = emotion.get('up_count', 0)
    
    # 读取3.0情绪规则
    try:
        _3e = load_config().get('3.0_emotion_rules', {})
        _aux = _3e.get('辅助_mode', {})
        allow_aux = _aux.get('allow_lowsuck', True)
        melt_below = _3e.get('melt_below', 1800)  # BUG-1修复：读配置，不再硬编码2000
    except:
        allow_aux = True
        melt_below = 1800
    
    # C+B：冰区(melt_below)且禁止低吸时才跳过
    if today_up < melt_below and not allow_aux:
        return []
    
    # 判定locked状态
    dim = emotion.get('dim', '')
    aux = emotion.get('aux', '')
    is_aux_mode = (dim == '辅助' or aux == '无')
    if is_aux_mode and today_up > 3500:
        locked = True
        locked_reason = '辅助模式·仅MA10低吸(≤1成)'
    elif today_up < melt_below:
        locked = True
        locked_reason = f'冰点·3.0熔断(<{melt_below})'
    else:
        # 连续2日>2500才完全激活
        state_file = Path(__file__).parent.parent / 'trading' / '系统状态.json'
        yesterday_up = 0
        if state_file.exists():
            try:
                with open(state_file) as f:
                    state = json.load(f)
                yesterday_up = state.get('yesterday', {}).get('up_count', 0)
                if not yesterday_up:
                    yesterday_up = state.get('today', {}).get('up_count', 0)
            except:
                pass
        if yesterday_up > 2500 and today_up > 2500:
            locked = False
            locked_reason = ''
        else:
            locked = True
            locked_reason = '等待连续2日>2500激活'
    
    candidates = []
    for s in trend_pool:
        code = s.get('code', '')
        name = s.get('name', '')
        amount_str = s.get('amount', '0')
        try:
            amount = float(amount_str)
        except:
            amount = 0
        
        # 从趋势池解析... v2.1字段映射
        status = s.get('status', '')   # 🔴/🟡/🟢 赛道状态
        note = s.get('note', '')       # 入池理由（含✅）
        ma_ok = '✅' in note
        
        score = 0
        if ma_ok:
            score += 20
        if '🔴' in status:
            score += 30
        elif '🟡' in status:
            score += 20
        _tc = load_config().get('3.0_trend', {})
        if amount >= 10:
            score += _tc.get('score_amount_ge_10', 15)
        elif amount >= 5:
            score += _tc.get('score_amount_ge_5', 10)
        
        # score_detail for 3.0
        sd = {}
        sd['均线得分'] = 20 if ma_ok else 0
        sd['赛道状态得分'] = 30 if '🔴' in status else (20 if '🟡' in status else 0)
        sd['成交额得分'] = _tc.get('score_amount_ge_10', 15) if amount >= 10 else (_tc.get('score_amount_ge_5', 10) if amount >= 5 else 0)
        
        candidates.append({
            'name': name, 'code': code,
            'logic': f"{s.get('track', '')}/{status}",
            'amount': amount,
            'note': f'均线{"多头" if ma_ok else "待验证"}+额{amount}亿',
            'score': score,
            'score_detail': sd,
            'locked': locked,
            'locked_reason': locked_reason
        })
    
    # 催化剂评分（NEW）
    if CATALYST_AVAILABLE:
        for c in candidates:
            track = c.get('logic', '').split('/')[0]  # 从 "赛道/状态" 取赛道名
            result = calculate_catalyst_score(track if track else c.get('name', ''))
            c['catalyst_score'] = result['score']
            c['catalyst_grade'] = result['grade']
            c['catalyst_action'] = get_catalyst_action(result['grade'])
    
    # 按催化剂等级排序
    if CATALYST_AVAILABLE:
        grade_order = {'S': 0, 'A': 1, 'B': 2, 'C': 3, 'D': 4}
        candidates.sort(key=lambda x: (grade_order.get(x.get('catalyst_grade', 'D'), 4), -x['score']))
    else:
        candidates.sort(key=lambda x: x['score'], reverse=True)
    
    # 从config读取min_score和top_n
    try:
        import json as _json
        with open(os.path.join(os.path.dirname(__file__), '..', 'lobster-config.json')) as _f:
            _cfg = _json.load(_f)
        min_score = _cfg.get('trend_pool', {}).get('hard_constraints', {}).get('min_score', 30)
        top_n = _cfg.get('3.0_trend', {}).get('top_n', 3)
    except:
        min_score, top_n = 30, 3

    candidates = [c for c in candidates if c['score'] >= min_score]
    candidates.sort(key=lambda x: x['score'], reverse=True)
    return candidates[:top_n]

# ==================== 主流程 ====================

def main():
    today = datetime.date.today().strftime('%Y-%m-%d')
    
    print(f"🦞 龙虾盘前选股引擎 v1.0 | {today}")
    
    # 0. 趋势池过期检查（>3个交易日未更新则告警）
    print("📋 趋势池新鲜度检查...")
    pool_stale = check_pool_staleness()
    
    # 1. 数据
    print("📥 获取市场数据...")
    indices = get_index()
    sh = indices.get('sh000001', {}).get('change', 0)
    sz = indices.get('sz399001', {}).get('change', 0)
    cy = indices.get('sz399006', {}).get('change', 0)
    print(f"  指数: 上证{sh}% 深证{sz}% 创业板{cy}%")
    
    ad = get_advance_decline()
    # get_advance_decline() 已改为兜底默认值，不再返回 None
    print(f"  涨跌: {ad['up']}涨/{ad['down']}跌 {ad.get('zt', '?')}涨停/{ad.get('dt', '?')}跌停")
    
    # 2. 情绪
    emotion = determine_emotion(ad)

    # 【BUGFIX 2026-07-01】up_count 必须在三重校验之前赋值，
    # 否则 today_up=0 导致极端值校验误判 halving(30→15)
    emotion['up_count'] = ad['up']

    # 情绪三重校验（v2.5）
    state_path = Path(__file__).resolve().parent.parent / "trading" / "系统状态.json"
    yesterday_up = None
    try:
        with open(state_path) as sf:
            state = json.load(sf)
        yesterday_up = state.get('yesterday', {}).get('up_count')
    except:
        pass
    emotion = emotion_triple_check_premarket(emotion, yesterday_up)

    print(f"📊 情绪: {ad['up']}家 → 主导{emotion['dim']} 辅助{emotion.get('aux','')} 仓位上限{emotion['pos_limit_pct']}%")
    
    # 2.5 竞价异动（thsdk集成）→ 在步骤3之前运行，用于交叉匹配候选池
    auction_anomalies = []
    auction_codes = set()
    auction_weight = 0
    try:
        config = load_config()
        thsdk_cfg = config.get('thsdk', {})
        if thsdk_cfg.get('enabled', True):
            print("📡 竞价异动监控(thsdk)...")
            auction_script = SCRIPT_DIR / 'lobster_auction_monitor.py'
            if auction_script.exists():
                r = subprocess.run(
                    [sys.executable, str(auction_script)],
                    capture_output=True, text=True, timeout=30,
                    cwd=str(ROOT)
                )
                auction_path = ROOT / 'trading' / 'auction_anomaly.json'
                if auction_path.exists():
                    with open(auction_path) as af:
                        auction_data = json.load(af)
                    auction_anomalies = auction_data.get('anomalies', [])
                    for a in auction_anomalies:
                        code = str(a.get('code', a.get('代码', '')))
                        if code:
                            auction_codes.add(code)
                    auction_weight = thsdk_cfg.get('auction_anomaly_weight', 10)
                    print(f"  ✅ 竞价异动: {len(auction_anomalies)}条, {len(auction_codes)}只标的")
                    if auction_anomalies:
                        # 打印前5条异动摘要
                        for a in auction_anomalies[:5]:
                            print(f"    {a.get('code','')} {a.get('name','')} {a.get('type','')}")
                else:
                    print("  ⚠️  竞价异动脚本未产出结果文件")
            else:
                print("  ⚠️  lobster_auction_monitor.py 不存在，跳过")
    except Exception as e:
        print(f"  ⚠️  竞价异动采集失败: {e}")
    
    # 3. 涨停数据
    print("📥 获取涨停数据...")
    yesterday_zt, yest_date = get_yesterday_zt()
    zt_sub = get_zt_sub()
    print(f"  昨日涨停池: {len(yesterday_zt)}只({yest_date}) 连板池: {len(zt_sub)}只")
    
    # 用连板池交叉更新涨停池的连板数（westock涨停池默认1板）
    sub_codes = set()
    for sub in zt_sub:
        code = str(sub.get('代码', ''))
        lb = sub.get('连板数', 2)
        try: lb = int(lb)
        except: lb = 2
        sub_codes.add(code)
        # 在涨停池中找到对应股票，更新连板数
        for s in yesterday_zt:
            if str(s.get('代码', '')) == code:
                s['昨日连板数'] = lb
                break
    
    # 补充涨停池的所属行业（用westock板块数据或搜索）
    _enrich_zt_sector(yesterday_zt)
    
    # 4. 选股
    print("🔍 选股中...")
    c1_first = select_10_first_to_second(yesterday_zt)
    c1_div = select_10_divergence(zt_sub, yesterday_zt)
    c2_sector = select_20_sector(yesterday_zt)
    trend_pool = get_trend_pool()
    c3_trend = select_30_trend(trend_pool, emotion)

    # 冰点期双收紧（v1.11：仓位+选股门槛同步收紧）
    up = ad['up']
    ice_tight = False
    if up < 1600:
        ice_tight = True
        # below_1600：仓位30% + 1.0分歧低吸直接暂停
        c1_div = []  # 冰点分歧低吸暂停
        print("❄️ 冰点区(<1600)：1.0分歧低吸已暂停，仅保留一进二")
    elif up < 2000:
        ice_tight = True
        # 1500-2000：仓位40% + 分歧低吸收紧
        # 只保留连板≥3的高板股
        c1_div_orig_len = len(c1_div)
        c1_div = [s for s in c1_div if s.get('lb', 0) >= 3]
        removed = c1_div_orig_len - len(c1_div)
        print(f"❄️ 修复期(1500-2000)：分歧低吸保留≥3板({c1_div_orig_len}→{len(c1_div)}只，剔除{removed}只)")

    # 4.5 竞价异动交叉匹配（提升候选池中同时在竞价异动里的股票优先级）
    if auction_codes and auction_weight > 0:
        auction_confirmed = []
        all_candidates = [c1_first, c1_div, c2_sector, c3_trend]
        dim_names = ['1.0一进二', '1.0分歧低吸', '2.0板块卡位', '3.0趋势低吸']
        for dim_idx, candidates in enumerate(all_candidates):
            for c in candidates:
                code = str(c.get('code', ''))
                if code in auction_codes:
                    c['score'] = c.get('score', 0) + auction_weight
                    c['auction_confirmed'] = True
                    c['auction_type'] = next(
                        (a.get('type', a.get('异动类型', '')) for a in auction_anomalies
                         if str(a.get('code', a.get('代码', ''))) == code),
                        ''
                    )
                    if code not in auction_confirmed:
                        auction_confirmed.append(code)
        if auction_confirmed:
            print(f"🔔 竞价异动交叉确认: {len(auction_confirmed)}只 [{', '.join(auction_confirmed)}] +{auction_weight}分")
            # 重新排序各维度（有竞价确认的排在前面）
            c1_first.sort(key=lambda x: (x.get('auction_confirmed', False), x.get('score', 0)), reverse=True)
            c1_div.sort(key=lambda x: (x.get('auction_confirmed', False), x.get('score', 0)), reverse=True)
            c2_sector.sort(key=lambda x: (x.get('auction_confirmed', False), x.get('score', 0)), reverse=True)
            c3_trend.sort(key=lambda x: (x.get('auction_confirmed', False), x.get('score', 0)), reverse=True)

    # 5. 输出JSON
    result = {
        'date': today,
        'version': 'v1.3-config-driven',
        'indices': {'上证': sh, '深证': sz, '创业板': cy},
        'emotion': {
            '上涨家数': ad['up'],
            '下跌家数': ad['down'],
            '涨停': ad.get('zt', 0),
            '跌停': ad.get('dt', 0),
            '主导维度': emotion['dim'],
            '辅助维度': emotion['aux'],
            '总仓位上限': emotion['pos_limit_pct'],
            '冰点收紧': ice_tight,  # v1.11: below_1600或1600-2000时True
            '冰点说明': 'below_1600全暂停1.0分歧低吸；1600-2000仅保留≥3板' if ice_tight else ''
        },
        'hot_sectors': fetch_hot_sectors(),
        'candidates': {
            '1.0一进二': [
                {'名称': s['name'], '代码': s['code'], '额': s['amount'],
                 'sector': s.get('sector', ''),
                 'hot_sector': s.get('hot_sector', False),
                 '催化剂': s.get('catalyst_grade', '?'),
                 '建议': s.get('catalyst_action', ''),
                 '备注': f"额{s['amount']}亿+{s.get('sector','')}",
                 'score_detail': s.get('score_detail', {})}
                for s in c1_first
            ],
            '1.0分歧低吸': [
                {'名称': s['name'], '代码': s['code'], '连板': s['lb'],
                 'sector': s.get('sector', ''),
                 'hot_sector': s.get('hot_sector', False),
                 '催化剂': s.get('catalyst_grade', '?'),
                 '建议': s.get('catalyst_action', ''),
                 '备注': f"{s['lb']}连板+{s.get('sector','')}{'🔥' if s.get('hot_sector') else ''}",
                 'score_detail': s.get('score_detail', {})}
                for s in c1_div
            ],
            '2.0板块卡位': [
                {'名称': s['name'], '代码': s['code'], '板块': s['sector'],
                 '额': s['amount'], 'sector_zt': s.get('sector_zt', 0),
                 'hot_sector': s.get('hot_sector', True),  # 2.0候选默认是热点板块
                 '催化剂': s.get('catalyst_grade', '?'),
                 '建议': s.get('catalyst_action', ''),
                 '备注': f"{s['sector']}({s['sector_zt']}家涨停)",
                 'score_detail': s.get('score_detail', {})}
                for s in c2_sector
            ],
            '3.0趋势低吸': [
                {'名称': s['name'], '代码': s['code'], '产业逻辑': s['logic'],
                 '额': s['amount'], 'sector': s.get('logic', '').split('/')[0],
                 'hot_sector': s.get('hot_sector', False),
                 '催化剂': s.get('catalyst_grade', '?'),
                 '建议': s.get('catalyst_action', ''),
                 '备注': s['note'],
                 'score_detail': s.get('score_detail', {}),
                 'locked': s.get('locked', False),
                 '锁定原因': s.get('locked_reason', '') if s.get('locked') else ''}
                for s in c3_trend
            ]
        }
    }
    
    # 修复备注里的板块统计
    # 1.0一进二的板块涨停数
    sector_count = {}
    for s in c1_first:
        sector_count[s['sector']] = sector_count.get(s['sector'], 0) + 1
    for c in result['candidates']['1.0一进二']:
        for s in c1_first:
            if s['code'] == c['代码']:
                c['备注'] = f"额{s['amount']}亿+{s['sector']}({sector_count.get(s['sector'],0)}家首板)"
                break
    
    out_path = str(ROOT / 'trading' / 'premarket_candidates.json')
    with open(out_path, 'w') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"✅ 已写入 {out_path}")
    
    # 6. 打印结果
    print(f"\n{'='*60}")
    print(f"✅ 龙虾盘前选股 {today}")
    print(f"- 情绪：{ad['up']}涨/{ad['down']}跌，{ad.get('zt',0)}涨停/{ad.get('dt',0)}跌停")
    print(f"- 主导维度：{emotion['dim']}，辅助维度：{emotion['aux']}")
    print(f"- 总仓位上限：{emotion['pos_limit_pct']}%")
    
    for tier_name, stocks in result['candidates'].items():
        print(f"\n【{tier_name}】（{len(stocks)}只）")
        if not stocks:
            print("  无符合条件的标的")
        for i, s in enumerate(stocks, 1):
            if tier_name == '1.0一进二':
                print(f"  {i}. {s['名称']}({s['代码']}) — {s['备注']}")
            elif tier_name == '1.0分歧低吸':
                print(f"  {i}. {s['名称']}({s['代码']}) — {s['备注']}")
            elif tier_name == '2.0板块卡位':
                print(f"  {i}. {s['名称']}({s['代码']}) — {s['备注']} 额{s['额']}亿")
            else:
                print(f"  {i}. {s['名称']}({s['代码']}) — {s['备注']}")
    
    print(f"\n📌 以上为候选池，09:25竞价阶段将从中筛选最优1只/档位")

if __name__ == '__main__':
    main()
