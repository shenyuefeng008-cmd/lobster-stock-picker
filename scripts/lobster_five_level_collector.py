#!/usr/bin/env python3
"""
五档快照采集器 — 盘中每分钟记录关注股买卖五档
用法: python3 lobster_five_level_collector.py [--interval 60]
数据输出: trading/five_level_snapshots/YYYYMMDD.jsonl
"""

import urllib.request, re, json, os, sys, time, datetime, signal

WS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SNAP_DIR = f"{WS}/trading/five_level_snapshots"
CANDIDATES_FILE = f"{WS}/trading/bid_result.json"
PREMARKET_FILE = f"{WS}/trading/premarket_candidates.json"
os.makedirs(SNAP_DIR, exist_ok=True)

# 采集间隔（秒）
INTERVAL = int(sys.argv[2]) if len(sys.argv) > 2 and sys.argv[1] == '--interval' else 60

# 默认关注股（无候选池时使用）
DEFAULT_CODES = {
    '郴电国际': 'sh600969',
    '华电能源': 'sh600726',
    '博敏电子': 'sh603936',
}

running = True

def signal_handler(sig, frame):
    global running
    running = False
    print("\n🛑 收到停止信号，保存数据退出...")

signal.signal(signal.SIGTERM, signal_handler)
signal.signal(signal.SIGINT, signal_handler)


def get_watchlist():
    """从候选池读取关注股，失败则用默认列表"""
    codes = {}
    
    # 尝试从竞价结果读取
    for fp in [CANDIDATES_FILE, PREMARKET_FILE]:
        if os.path.exists(fp):
            try:
                with open(fp) as f:
                    data = json.load(f)
                # 兼容多种格式
                cands = data.get('candidates') or data.get('passed') or data
                if isinstance(cands, dict):
                    for dim, stocks in cands.items():
                        if isinstance(stocks, list):
                            for s in stocks:
                                name = s.get('名称', s.get('name', ''))
                                code = s.get('代码', s.get('code', ''))
                                if name and code:
                                    prefix = 'sh' if str(code).startswith('6') else 'sz'
                                    codes[name] = f"{prefix}{code}"
            except:
                continue
    
    if not codes:
        codes = DEFAULT_CODES
    
    return codes


def fetch_five_levels(codes):
    """批量获取五档数据"""
    if not codes:
        return []
    
    url_str = ','.join(set(codes.values()))
    url = f"https://qt.gtimg.cn/q={url_str}"
    
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    try:
        raw = urllib.request.urlopen(req, timeout=10).read()
    except Exception as e:
        print(f"  ⚠️ 网络错误: {e}")
        return []
    
    for enc in ['gb2312', 'gbk', 'gb18030']:
        try:
            text = raw.decode(enc)
            break
        except:
            continue
    
    results = []
    for line in text.strip().split(';'):
        line = line.strip()
        if not line:
            continue
        m = re.search(r'"(.+)"', line)
        if not m:
            continue
        p = m.group(1).split('~')
        if len(p) < 30:
            continue
        
        try:
            d = {
                'time': datetime.datetime.now().strftime('%H:%M:%S'),
                'name': p[1],
                'code': p[2],
                'price': float(p[3]),
                'pct': round(float(p[32]), 2),
                'ask': [{'price': round(float(p[19+i*2]), 2), 'vol': int(p[20+i*2])} for i in range(5)],
                'bid': [{'price': round(float(p[9+i*2]), 2), 'vol': int(p[10+i*2])} for i in range(5)],
            }
            # 计算买卖比
            ta = sum(a['vol'] for a in d['ask'])
            tb = sum(b['vol'] for b in d['bid'])
            d['ask_total'] = ta
            d['bid_total'] = tb
            d['ratio'] = round(ta / tb, 2) if tb > 0 else 0
            results.append(d)
        except (ValueError, IndexError):
            continue
    
    return results


def is_trading_time():
    """判断当前是否在交易时段"""
    now = datetime.datetime.now()
    # 非工作日跳过
    if now.weekday() >= 5:
        return False
    t = now.hour * 100 + now.minute
    return (925 <= t <= 1130) or (1300 <= t <= 1500)


def main():
    today = datetime.datetime.now().strftime('%Y%m%d')
    out_file = f"{SNAP_DIR}/{today}.jsonl"
    
    codes = get_watchlist()
    print(f"📊 五档采集启动 | 关注{len(codes)}只 | 间隔{INTERVAL}s | 输出: {out_file}")
    print(f"   关注: {', '.join(codes.keys())}")
    print(f"   交易时段: 9:25-11:30, 13:00-15:00")
    print()
    
    count = 0
    last_minute = -1
    
    while running:
        now = datetime.datetime.now()
        
        # 15:05后自动退出
        if now.hour >= 15 and now.minute >= 5:
            print(f"\n✅ 15:05，采集结束。共{count}条快照 → {out_file}")
            break
        
        # 只在交易时段采集
        if not is_trading_time():
            time.sleep(INTERVAL)
            continue
        
        # 避免同一分钟重复采集
        current_minute = now.hour * 60 + now.minute
        if current_minute == last_minute:
            time.sleep(5)
            continue
        last_minute = current_minute
        
        # 采集
        results = fetch_five_levels(codes)
        if results:
            with open(out_file, 'a') as f:
                for r in results:
                    f.write(json.dumps(r, ensure_ascii=False) + '\n')
            count += 1
            
            # 每10次打印一次进度
            if count % 10 == 0:
                print(f"  ⏱ {now.strftime('%H:%M:%S')} 已采集{count}条")
        
        time.sleep(INTERVAL)
    
    print(f"📁 数据文件: {out_file}")
    if os.path.exists(out_file):
        lines = sum(1 for _ in open(out_file))
        size = os.path.getsize(out_file)
        print(f"   {lines}条记录, {size/1024:.1f}KB")


if __name__ == '__main__':
    main()
