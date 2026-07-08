#!/usr/bin/env python3
"""
涨跌家数获取脚本 - v4（纯腾讯API版本）
直接用腾讯API获取全市场涨跌家数，不依赖legulegu.com
"""
import subprocess, re, json, time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CACHE_FILE = ROOT / 'trading' / 'sentiment_cache.json'
CACHE_TTL = 120  # 2分钟缓存

def get_market_sentiment_tencent():
    """
    主源：腾讯API + 东方财富Web接口
    返回：(up, down, zt, dt) 或 (-1, -1, -1, -1)
    """
    # 方案1：东方财富API（最稳定）
    try:
        url = "http://push2.eastmoney.com/api/qt/clist/get?cb=&pn=1&pz=1&fs=m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23&fields=f3"
        r = subprocess.run(['curl', '-s', '-L', '--max-time', '10', '-A', 'Mozilla/5.0', url], 
                          capture_output=True, text=True, timeout=12)
        # 这个接口返回的是分页数据，需要换一个
    except:
        pass
    
    # 方案2：腾讯API采樣（改进版）
    # 用更合理的代码范围
    try:
        # 上证：600xxx ~ 605xxx，深证：000xxx ~ 002xxx, 300xxx
        sample_ranges = [
            # 上证主板
            ('sh600000', 10), ('sh600100', 10), ('sh600200', 10), ('sh600300', 10),
            ('sh600400', 10), ('sh600500', 10), ('sh600600', 10), ('sh600700', 10),
            ('sh600800', 10), ('sh600900', 10), ('sh601000', 10), ('sh601100', 10),
            ('sh601200', 10), ('sh601300', 10), ('sh601400', 10), ('sh601500', 10),
            ('sh601600', 10), ('sh601700', 10), ('sh601800', 10), ('sh601900', 10),
            # 深证主板
            ('sz000001', 5), ('sz000100', 5), ('sz000200', 5), ('sz000300', 5),
            ('sz000500', 5), ('sz000600', 5), ('sz000700', 5), ('sz000800', 5),
            ('sz000900', 5), ('sz001000', 5), ('sz001100', 5), ('sz001200', 5),
            # 中小板
            ('sz002001', 5), ('sz002100', 5), ('sz002200', 5), ('sz002300', 5),
            ('sz002400', 5), ('sz002500', 5), ('sz002600', 5), ('sz002700', 5),
            ('sz002800', 5), ('sz002900', 5),
            # 创业板
            ('sz300001', 5), ('sz300100', 5), ('sz300200', 5), ('sz300300', 5),
            ('sz300400', 5), ('sz300500', 5), ('sz300600', 5), ('sz300700', 5),
            ('sz300800', 5), ('sz300900', 5),
        ]
        
        codes = []
        for code, count in sample_ranges:
            num = int(code[2:])
            prefix = code[:2]
            for i in range(count):
                test_code = f"{prefix}{num + i*10:06d}"
                codes.append(test_code)
        
        # 批量查询
        url = f"https://qt.gtimg.cn/q={','.join(codes)}"
        r = subprocess.run(['curl', '-s', '-L', '--max-time', '15', '-A', 'Mozilla/5.0', url],
                          capture_output=True)
        text = r.stdout.decode('gbk', errors='ignore')
        
        up = down = flat = 0
        valid = 0
        for line in text.strip().split('\n'):
            if not line.startswith('v_'):
                continue
            try:
                parts = line.split('~')
                if len(parts) < 33:
                    continue
                # p[32] = 涨跌幅
                pct = float(parts[32])
                valid += 1
                if pct > 0:
                    up += 1
                elif pct < 0:
                    down += 1
                else:
                    flat += 1
            except:
                continue
        
        if valid >= 50:  # 至少50个有效样本
            # 估算全市场（A股约5000只）
            ratio_up = up / valid
            ratio_down = down / valid
            total_est = 5000
            return int(ratio_up * total_est), int(ratio_down * total_est), 0, 0
    except Exception as e:
        print(f"[tencent] 采样失败: {e}")
    
    return -1, -1, -1, -1

def get_sentiment_with_cache():
    """带缓存的涨跌家数获取"""
    now = time.time()
    
    # 读缓存
    if CACHE_FILE.exists():
        try:
            cache = json.loads(CACHE_FILE.read_text())
            if now - cache.get('timestamp', 0) < CACHE_TTL:
                return cache['up'], cache['down'], cache.get('zt', 0), cache.get('dt', 0)
        except:
            pass
    
    # 获取新数据
    up, down, zt, dt = get_market_sentiment_tencent()
    
    # 写缓存
    if up > 0 and down > 0:
        CACHE_FILE.write_text(json.dumps({
            'up': up, 'down': down, 'zt': zt, 'dt': dt,
            'timestamp': now, 'src': 'tencent_sample'
        }))
    
    return up, down, zt, dt

if __name__ == '__main__':
    up, down, zt, dt = get_sentiment_with_cache()
    print(f"上涨: {up} | 下跌: {down} | 涨停: {zt} | 跌停: {dt}")
