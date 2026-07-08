#!/usr/bin/env python3
"""
龙虾动态产业图谱采集脚本 v1.0
每日收盘后自动运行，构建/更新 trading/产业图谱.json

数据源：
  1. akshare 涨停池 → 按板块聚合涨停家数/成交额
  2. 腾讯日K线 → 池中标的偏离MA10中位数
  3. 产业逻辑框架.md → 赛道基础状态

输出：
  trading/产业图谱.json（每日覆盖）
  trading/产业图谱.md（人类可读摘要）
"""

import json, re, subprocess, sys, datetime, time, signal
from pathlib import Path
from collections import defaultdict

SCRIPT_TIMEOUT = 180

def timeout_handler(signum, frame):
    print("\n⚠️ 脚本执行超时，强制退出")
    sys.exit(1)

signal.signal(signal.SIGALRM, timeout_handler)
signal.alarm(SCRIPT_TIMEOUT)

WS = Path("/Users/yuefengshen/.qclaw/workspace-1gwpiwf3hr163jz5")
GRAPH_JSON = WS / "trading/产业图谱.json"
GRAPH_MD = WS / "trading/产业图谱.md"
FRAMEWORK_MD = WS / "trading/产业逻辑框架.md"
POOL_MD = WS / "trading/趋势容量池.md"
CONFIG_JSON = WS / "lobster-config.json"

# ===== 工具函数 =====
def http_get(url, retries=3, timeout=15):
    """带重试的HTTP GET"""
    for i in range(retries):
        r = subprocess.run(
            ["curl", "-s", "-L", "--max-time", str(timeout),
             "-A", "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
             url],
            capture_output=True
        )
        if r.returncode == 0 and len(r.stdout.decode("gbk", errors="ignore")) > 50:
            return r.stdout.decode("gbk", errors="ignore")
        time.sleep(2 ** i)
    return None

def get_qq_kline(code, days=30):
    """腾讯日K线（不复权）"""
    url = f"https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?_var=kline_dayqfq&param={code},day,,,{days},qfq"
    text = http_get(url)
    if not text:
        return None
    try:
        json_str = text[text.index('=') + 1:]
        data = json.loads(json_str)
        key = list(data['data'].keys())[0]
        return data['data'][key].get('qfqday') or data['data'][key].get('day')
    except:
        return None

def calc_ma(closes, n):
    if len(closes) < n:
        return None
    return sum(closes[-n:]) / n

def parse_framework():
    """解析产业逻辑框架.md → 赛道基础状态"""
    if not FRAMEWORK_MD.exists():
        return {}
    text = FRAMEWORK_MD.read_text()
    sectors = {}

    # 赛道名称标准化映射
    SECTOR_ALIAS = {
        # 液冷
        '液冷': '液冷', '液冷散热': '液冷', '冷却液': '液冷', '数据中心液冷': '液冷',
        # IDC/AIDC
        'IDC': 'IDC/AIDC', 'AIDC': 'IDC/AIDC', 'IDC/AIDC': 'IDC/AIDC', '数据中心': 'IDC/AIDC', '算力中心': 'IDC/AIDC',
        # 燃气轮机
        '燃气轮机': '燃气轮机', '燃机': '燃气轮机', '燃气发电机': '燃气轮机',
        # 存储超级周期
        '存储超级周期': '存储超级周期', '存储': '存储超级周期', '存储/HBM': '存储超级周期', 'HBM': '存储超级周期',
        '存储芯片': '存储超级周期', '高带宽内存': '存储超级周期',
        # 有色金属/工业金属
        '有色金属/工业金属': '有色金属/工业金属', '有色金属': '有色金属/工业金属', '工业金属': '有色金属/工业金属',
        '铜': '有色金属/工业金属', '铝': '有色金属/工业金属', '小金属': '有色金属/工业金属',
        # 国产芯片(昇腾)
        '国产芯片(昇腾)': '国产芯片(昇腾)', '国产芯片': '国产芯片(昇腾)', '昇腾': '国产芯片(昇腾)',
        '半导体': '国产芯片(昇腾)', '芯片': '国产芯片(昇腾)', '集成电路': '国产芯片(昇腾)',
        # 光纤
        '光纤': '光纤', '光纤/光缆': '光纤', '光缆': '光纤', '光纤光缆': '光纤', '特种光纤': '光纤',
        # 电力
        '电力': '电力', '电网设备': '电力', '火电': '电力', '绿电': '电力', '新能源发电': '电力',
        # 光模块
        '光模块': '光模块', '光模块/InP': '光模块', '光模块/存储': '光模块', 'InP': '光模块', '光芯片': '光模块', '光学模块': '光模块',
        # BBU/钠电
        'BBU/钠电': 'BBU/钠电', 'BBU': 'BBU/钠电', '钠电': 'BBU/钠电', 'BBU/电源': 'BBU/钠电',
        '备用电源': 'BBU/钠电', '服务器电源': 'BBU/钠电', '电源': 'BBU/钠电',
        # 陶瓷基板
        '陶瓷基板': '陶瓷基板', '陶瓷基板/HDI': '陶瓷基板',
        # 国产光刻机
        '国产光刻机': '国产光刻机', '光刻机': '国产光刻机', 'SSA800': '国产光刻机',
        # 工程器械
        '工程器械': '工程器械', '工程机械': '工程器械', '挖机': '工程器械', '机床': '工程器械',
        # SOFC
        'SOFC': 'SOFC', 'SOFC/SOEC': 'SOFC', '固体氧化物燃料电池': 'SOFC', '燃料电池': 'SOFC',
        # 化工（氟化工）
        '化工（氟化工）': '化工（氟化工）', '化工': '化工（氟化工）', '氟化工': '化工（氟化工）',
        '化工/氟化工': '化工（氟化工）', '氟化工/化工': '化工（氟化工）', '化学制品': '化工（氟化工）',
        '制冷剂': '化工（氟化工）', '磷化工': '化工（氟化工）',
        # 汽车零部件
        '汽车零部件': '汽车零部件', '汽车零部': '汽车零部件', '智能驾驶': '汽车零部件',
        # 国产Switch芯片
        '国产Switch芯片': '国产Switch芯片', '国产Switch': '国产Switch芯片', 'Switch芯片': '国产Switch芯片',
        'ICN Switch': '国产Switch芯片',
        # SerDes/裕太微
        'SerDes/裕太微': 'SerDes/裕太微', 'SerDes': 'SerDes/裕太微', '裕太微': 'SerDes/裕太微',
        # DCI
        'DCI': 'DCI', 'DCI互联': 'DCI', '数据中心互联': 'DCI',
        # HVLP铜箔
        'HVLP铜箔': 'HVLP铜箔', '铜箔': 'HVLP铜箔', '高速CCL': 'HVLP铜箔',
        # 电子特气
        '电子特气': '电子特气', '电子化学': '电子特气', '六氟化钨': '电子特气',
    }

    # 匹配 赛道名 | 状态 | ... 格式
    # 例：| 液冷 | AIDC建设加速... | 🔴 超级短缺 |
    pattern = re.compile(r'^\|\s*([^|\n]+?)\s*\|\s*[^|]*\|\s*([🔴🟡🟢][^|]+)', re.MULTILINE)
    for m in pattern.finditer(text):
        raw_name = m.group(1).strip()
        status = m.group(2).strip()
        name = SECTOR_ALIAS.get(raw_name, raw_name)
        if name != '其他' and len(name) > 1:
            sectors[name] = {'status': status, 'last_updated': datetime.date.today().isoformat()}

    return sectors

def get_zt_pool(date_str):
    """获取涨停池，按板块聚合"""
    try:
        import akshare as ak
        df = ak.stock_zt_pool_em(date=date_str)
        if df is None or df.empty:
            return {}
        # 按板块聚合
        board_stats = defaultdict(lambda: {'zt_count': 0, 'codes': []})
        for _, row in df.iterrows():
            board = str(row.get('板块', '')).strip()
            if board and board not in ('nan', 'None'):
                board_stats[board]['zt_count'] += 1
                code = str(row.get('代码', ''))
                board_stats[board]['codes'].append(code)
        return dict(board_stats)
    except Exception as e:
        print(f"  ⚠️ 涨停池获取失败: {e}")
        return {}

def get_sector_turnover(board_name):
    """通过涨停池中板块的成交额估算板块热度"""
    # 简化：涨停家数代理成交额
    return {}

def build_sector_map():
    """构建动态产业图谱"""
    today = datetime.date.today().strftime("%Y%m%d")
    today_human = datetime.date.today().strftime("%Y-%m-%d")
    print(f"\n{'='*60}")
    print(f"📊 动态产业图谱 v1.0 | {today_human}")
    print(f"{'='*60}")

    # 步骤1：解析产业逻辑框架（赛道基础状态）
    print("\n📋 步骤1：读取产业逻辑框架...")
    framework_sectors = parse_framework()
    print(f"  已解析 {len(framework_sectors)} 个赛道状态")
    for k, v in list(framework_sectors.items())[:5]:
        print(f"  {k}: {v['status']}")

    # 步骤2：从趋势池读取标的 → 关联赛道
    print("\n📋 步骤2：读取趋势池标的...")
    pool_stocks = {}  # code -> {name, sector, score}
    if POOL_MD.exists():
        text = POOL_MD.read_text()
        # 匹配 | 工业富联 | 601138 | IDC/AIDC | ...（代码无sh/sz前缀）
        pattern = re.compile(r'^\|\s*([^|\n]+?)\s*\|\s*(\d{6})\s*\|\s*([^|\n]+?)\s*\|', re.MULTILINE)
        for m in pattern.finditer(text):
            name = m.group(1).strip()
            code = m.group(2).strip()
            sector = m.group(3).strip()
            # 自动加 sh/sz 前缀
            code_prefixed = 'sh' + code if code.startswith('6') else 'sz' + code
            pool_stocks[code_prefixed] = {'name': name, 'sector': sector}
    print(f"  趋势池共 {len(pool_stocks)} 只标的")

    # 步骤3：获取涨停池（今日）
    print("\n📋 步骤3：获取涨停池（板块聚合）...")
    zt_board = get_zt_pool(today)
    print(f"  涨停池共 {sum(v['zt_count'] for v in zt_board.values())} 只涨停，归属 {len(zt_board)} 个板块")

    # 步骤4：计算各赛道标的的偏离MA10数据
    print("\n📋 步骤4：计算池中标的偏离MA10...")
    sector_dev = defaultdict(list)  # sector -> [dev_pct, ...]
    for code, info in pool_stocks.items():
        kline = get_qq_kline(code, 30)
        if not kline or len(kline) < 10:
            continue
        closes = [float(d[2]) for d in kline]
        ma10 = calc_ma(closes, 10)
        if ma10:
            dev = (closes[-1] / ma10 - 1) * 100
            sector_dev[info['sector']].append(round(dev, 2))

    # 步骤5：综合构建图谱
    print("\n📋 步骤5：综合评分...")

    # 赛道列表（从框架获取 + 趋势池补充）
    all_sectors = set(framework_sectors.keys())
    for info in pool_stocks.values():
        all_sectors.add(info['sector'])

    graph = {
        'meta': {
            'version': '1.0',
            'date': today_human,
            'created_at': datetime.datetime.now().isoformat(),
            'source': '动态采集（akshare涨停池+腾讯K线+产业逻辑框架）'
        },
        'sectors': {}
    }

    # 定义赛道 → 板块关键词映射（用于匹配涨停池板块名）
    SECTOR_KEYWORDS = {
        'IDC/AIDC': ['算力', 'AI算力', 'IDC', '数据中心', '算力租赁', 'AIDC'],
        '光模块': ['光模块', '光通信', '光器件'],
        '光纤': ['光纤', '光缆', '特种光纤'],
        '燃气轮机': ['燃气轮机', '燃气发电', '电力设备'],
        '氟化工': ['氟化工', '氟', '氢氟酸', '制冷剂'],
        '液冷': ['液冷', '温控', '散热'],
        '存储': ['存储', 'HBM', '存储器'],
        '电力': ['电力', '电网', '输配电', '绿电'],
    }

    # 匹配涨停池板块
    def match_board(board_name, sector):
        keywords = SECTOR_KEYWORDS.get(sector, [])
        for kw in keywords:
            if kw in board_name:
                return True
        return board_name == sector

    # 评分函数
    def calc_sector_score(sector, zt_count, dev_list, framework_status):
        score = 0
        heat = '🟢'
        warnings = []

        # 涨停家数评分（最多+20分）
        if zt_count >= 5:
            score += 20
            heat = '🔴'
        elif zt_count >= 3:
            score += 12
            heat = '🟡'
        elif zt_count >= 1:
            score += 5

        # 偏离MA10评分（最多+30分，偏离越大越危险→降分）
        if dev_list:
            avg_dev = sum(dev_list) / len(dev_list)
            # 正常偏离：<3% → +30分
            if avg_dev < 0:
                score += 30  # 回调到位
            elif avg_dev < 3:
                score += 30
            elif avg_dev < 5:
                score += 20
            elif avg_dev < 10:
                score += 10
                heat = '🟡'
            else:
                score += 0
                heat = '🔴'
                warnings.append('⚠️板块过热，偏离MA10中位数+{:.1f}%'.format(avg_dev))

        # 框架状态加成（最多+50分）
        if '超级短缺' in framework_status or '短缺确认' in framework_status:
            score += 50
        elif '产能爬坡' in framework_status:
            score += 30
        elif '转折' in framework_status or '加仓' in framework_status:
            score += 20
        elif '早期' in framework_status:
            score += 10

        return {
            'score': min(score, 100),
            'heat': heat,
            'warnings': warnings,
            'dev_ma10_median': round(sum(dev_list)/len(dev_list), 2) if dev_list else None
        }

    for sector in sorted(all_sectors):
        fw = framework_sectors.get(sector, {})
        fw_status = fw.get('status', '🟢未知')

        # 统计该赛道涨停家数
        zt_count = 0
        for board, data in zt_board.items():
            if match_board(board, sector):
                zt_count += data['zt_count']

        dev_list = sector_dev.get(sector, [])
        result = calc_sector_score(sector, zt_count, dev_list, fw_status)

        graph['sectors'][sector] = {
            'framework_status': fw_status,
            'dynamic_heat': result['heat'],
            'zt_count_today': zt_count,
            'pool_dev_ma10_median': result['dev_ma10_median'],
            'score': result['score'],
            'warnings': result['warnings'],
            'pool_stocks': [info['name'] for info in pool_stocks.values() if info['sector'] == sector]
        }

    # 排序：得分高的在前
    graph['sectors'] = dict(sorted(
        graph['sectors'].items(),
        key=lambda x: x[1]['score'],
        reverse=True
    ))

    # 输出摘要
    print(f"\n📊 产业图谱摘要（共 {len(graph['sectors'])} 个赛道）")
    print(f"{'赛道':<12} {'框架状态':<12} {'热度':<4} {'涨停':>4} {'偏离MA10':>9} {'得分':>5} {'备注'}")
    print("-" * 70)
    for sector, data in graph['sectors'].items():
        dev = data['pool_dev_ma10_median']
        dev_str = f"{dev:+.1f}%" if dev is not None else "-"
        warns = '; '.join(data['warnings']) if data['warnings'] else ''
        print(f"{sector:<12} {data['framework_status']:<12} {data['dynamic_heat']:<4} "
              f"{data['zt_count_today']:>4} {dev_str:>9} {data['score']:>5} {warns}")

    # 保存JSON
    GRAPH_JSON.write_text(json.dumps(graph, ensure_ascii=False, indent=2))
    print(f"\n✅ 产业图谱已写入: {GRAPH_JSON}")

    # 产业图谱.md 已废弃 — 仅保留 .json 版本（消费者：DAILY_EVOLUTION）

    return graph

if __name__ == '__main__':
    try:
        build_sector_map()
    except KeyboardInterrupt:
        print("\n⚠️ 用户中断")
        sys.exit(1)

# ===== 纯腾讯接口版本（无akshare依赖）=====
def get_tencent_sector_data():
    """用趋势池标的实时涨幅代理板块热度（纯腾讯接口）"""
    import subprocess
    
    # 板块代码映射（腾讯qt.gtimg.cn）
    SECTOR_CODE_MAP = {
        '光模块': 'bk0478',  # 东方财富板块代码
        '光纤': 'bk0489',
        'IDC/AIDC': 'bk0501',
        '氟化工': 'bk0455',
        '燃气轮机': 'bk0888',
        '电力': 'bk0428',
    }
    
    # 方案1：用趋势池标的平均涨幅代理板块热度
    # 读取趋势池标的实时涨幅
    pool_stocks = {}
    if POOL_MD.exists():
        text = POOL_MD.read_text()
        pattern = re.compile(r'^\|\s*([^|\n]+?)\s*\|\s*(\d{6})\s*\|\s*([^|\n]+?)\s*\|', re.MULTILINE)
        for m in pattern.finditer(text):
            code = m.group(2).strip()
            sector = m.group(3).strip()
            code_prefixed = 'sh' + code if code.startswith('6') else 'sz' + code
            pool_stocks[code_prefixed] = {'name': m.group(1).strip(), 'sector': sector}
    
    # 批量获取实时行情
    codes = list(pool_stocks.keys())
    if not codes:
        return {}
    
    url = f"https://qt.gtimg.cn/q={','.join(codes)}"
    r = subprocess.run(
        ["curl", "-s", "-L", "--max-time", "10",
         "-A", "Mozilla/5.0", url],
        capture_output=True
    )
    
    if r.returncode != 0:
        return {}
    
    # 解析行情数据（腾讯接口返回GBK编码）
    sector_chg = defaultdict(list)  # sector -> [chg_pct, ...]
    text = r.stdout.decode('gbk', errors='ignore') if isinstance(r.stdout, bytes) else r.stdout
    for line in text.strip().split('\n'):
        if not line.startswith('v_'):
            continue
        try:
            # 格式：v_sh601138="1~工业富联~601138~...
            parts = line.split('~')
            if len(parts) < 33:
                continue
            # 提取代码：v_sh601138="1 → sh601138
            code_raw = parts[0]  # v_sh601138="1
            code = code_raw.split('=')[0].replace('v_', '')  # sh601138
            chg_pct = float(parts[32])  # 第33字段：涨跌幅
            if code in pool_stocks:
                sector = pool_stocks[code]['sector']
                sector_chg[sector].append(chg_pct)
                print(f"  {pool_stocks[code]['name']}({code}): {chg_pct:+.2f}%")
        except Exception as e:
            print(f"  解析失败: {e}")
            continue
    
    # 计算板块平均涨幅
    result = {}
    for sector, chgs in sector_chg.items():
        if chgs:
            result[sector] = {
                'avg_chg': round(sum(chgs)/len(chgs), 2),
                'count': len(chgs),
                'max_chg': max(chgs),
                'min_chg': min(chgs)
            }
    return result


def build_sector_map_tencent():
    """纯腾讯接口版本（无akshare依赖）"""
    today_human = datetime.date.today().strftime("%Y-%m-%d")
    print(f"\n{'='*60}")
    print(f"📊 动态产业图谱 v1.0（纯腾讯版）| {today_human}")
    print(f"{'='*60}")

    # 步骤1：解析产业逻辑框架
    print("\n📋 步骤1：读取产业逻辑框架...")
    framework_sectors = parse_framework()
    print(f"  已解析 {len(framework_sectors)} 个赛道状态")

    # 步骤2：读取趋势池标的
    print("\n📋 步骤2：读取趋势池标的...")
    pool_stocks = {}
    if POOL_MD.exists():
        text = POOL_MD.read_text()
        pattern = re.compile(r'^\|\s*([^|\n]+?)\s*\|\s*(\d{6})\s*\|\s*([^|\n]+?)\s*\|', re.MULTILINE)
        for m in pattern.finditer(text):
            name = m.group(1).strip()
            code = m.group(2).strip()
            sector = m.group(3).strip()
            code_prefixed = 'sh' + code if code.startswith('6') else 'sz' + code
            pool_stocks[code_prefixed] = {'name': name, 'sector': sector}
    print(f"  趋势池共 {len(pool_stocks)} 只标的")

    # 步骤3：获取趋势池标的实时涨幅（腾讯）
    print("\n📋 步骤3：获取标的实时涨幅（腾讯）...")
    sector_chg = get_tencent_sector_data()
    print(f"  已获取 {len(sector_chg)} 个赛道的实时涨幅")

    # 步骤4：计算各赛道偏离MA10
    print("\n📋 步骤4：计算池中标的偏离MA10...")
    sector_dev = defaultdict(list)
    for code, info in pool_stocks.items():
        kline = get_qq_kline(code, 30)
        if not kline or len(kline) < 10:
            continue
        closes = [float(d[2]) for d in kline]
        ma10 = calc_ma(closes, 10)
        if ma10:
            dev = (closes[-1] / ma10 - 1) * 100
            sector_dev[info['sector']].append(round(dev, 2))

    # 步骤5：综合评分
    print("\n📋 步骤5：综合评分...")
    
    all_sectors = set(framework_sectors.keys())
    for info in pool_stocks.values():
        all_sectors.add(info['sector'])

    graph = {
        'meta': {
            'version': '1.0',
            'date': today_human,
            'created_at': datetime.datetime.now().isoformat(),
            'source': '纯腾讯接口（无akshare依赖）'
        },
        'sectors': {}
    }

    for sector in sorted(all_sectors):
        fw = framework_sectors.get(sector, {})
        fw_status = fw.get('status', '🟢未知')
        
        # 板块平均涨幅
        chg_data = sector_chg.get(sector, {})
        avg_chg = chg_data.get('avg_chg', 0)
        max_chg = chg_data.get('max_chg', 0)
        
        # 偏离MA10
        dev_list = sector_dev.get(sector, [])
        avg_dev = sum(dev_list)/len(dev_list) if dev_list else None
        
        # 评分逻辑（简化版）
        score = 0
        heat = '🟢'
        warnings = []
        
        # 框架状态（50分）
        if '超级短缺' in fw_status or '短缺确认' in fw_status:
            score += 50
        elif '产能爬坡' in fw_status:
            score += 30
        elif '转折' in fw_status:
            score += 20
        
        # 平均涨幅（20分）
        if abs(avg_chg) > 5:
            score += 20
            heat = '🔴'
        elif abs(avg_chg) > 3:
            score += 15
            heat = '🟡'
        elif abs(avg_chg) > 1:
            score += 10
        
        # 偏离MA10（30分）
        if avg_dev is not None:
            if avg_dev > 10:
                score += 0
                heat = '🔴'
                warnings.append(f'⚠️板块过热，偏离MA10中位数+{avg_dev:.1f}%')
            elif avg_dev > 5:
                score += 10
                heat = '🟡'
            elif avg_dev < 0:
                score += 30  # 回调到位
            else:
                score += 20
        
        graph['sectors'][sector] = {
            'framework_status': fw_status,
            'dynamic_heat': heat,
            'avg_chg_today': avg_chg,
            'pool_dev_ma10_median': round(avg_dev, 2) if avg_dev is not None else None,
            'score': min(score, 100),
            'warnings': warnings,
            'pool_stocks': [info['name'] for info in pool_stocks.values() if info['sector'] == sector]
        }
    
    # 排序
    graph['sectors'] = dict(sorted(graph['sectors'].items(), key=lambda x: x[1]['score'], reverse=True))
    
    # 输出摘要
    print(f"\n📊 产业图谱摘要（共 {len(graph['sectors'])} 个赛道）")
    print(f"{'赛道':<12} {'框架状态':<12} {'热度':<4} {'均涨%':>6} {'偏离MA10':>9} {'得分':>5} 备注")
    print("-" * 70)
    for sector, data in graph['sectors'].items():
        dev = data['pool_dev_ma10_median']
        dev_str = f"{dev:+.1f}%" if dev is not None else "-"
        chg_str = f"{data['avg_chg_today']:+.2f}" if data['avg_chg_today'] else "-"
        warns = '; '.join(data['warnings']) if data['warnings'] else ''
        print(f"{sector:<12} {data['framework_status']:<12} {data['dynamic_heat']:<4} "
              f"{chg_str:>6} {dev_str:>9} {data['score']:>5} {warns}")
    
    # 保存JSON
    GRAPH_JSON.write_text(json.dumps(graph, ensure_ascii=False, indent=2))
    print(f"\n✅ 产业图谱已写入: {GRAPH_JSON}")
    
    # 生成MD
    md = f"# 📊 动态产业图谱 v1.0（纯腾讯版）\n\n> 生成时间：{today_human}\n"
    md += "> 数据源：腾讯实时行情 + 腾讯K线 + 产业逻辑框架\n\n## 赛道热度\n\n"
    md += "| 赛道 | 框架状态 | 动态热度 | 均涨% | 偏离MA10 | 得分 | 备注 |\n"
    md += "|------|---------|--------|------|---------|------|------|\n"
    for sector, data in graph['sectors'].items():
        dev = data['pool_dev_ma10_median']
        dev_str = f"{dev:+.1f}%" if dev is not None else "-"
        chg_str = f"{data['avg_chg_today']:+.2f}" if data['avg_chg_today'] else "-"
        warns = '; '.join(data['warnings']) if data['warnings'] else '-'
        md += f"| {sector} | {data['framework_status']} | {data['dynamic_heat']} | {chg_str} | {dev_str} | {data['score']} | {warns} |\n"
    
    GRAPH_MD.write_text(md)
    print(f"✅ 产业图谱摘要已写入: {GRAPH_MD}")
    
    return graph


if __name__ == '__main__':
    import sys
    # 默认用纯腾讯版本
    if '--akshare' in sys.argv:
        build_sector_map()
    else:
        build_sector_map_tencent()
