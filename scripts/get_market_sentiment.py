#!/usr/bin/env python3
"""
涨跌家数获取脚本 - v3（修复 group(2) 索引错误）
主源：legulegu.com（直接全市场数据）
备源：腾讯行情接口（仅在主源失效时用采样估算）
"""
import urllib.request
import time
import json
import os
import subprocess
import re

CACHE_FILE = '/tmp/lobster_sentiment_cache.json'
CACHE_TTL = 120  # 2分钟缓存


def get_market_sentiment_legulegu():
    """
    主源：从legulegu.com获取涨跌家数（直接数据，精确）
    """
    try:
        result = subprocess.run(
            ['curl', '-sL', '--max-time', '15', '-A', 'Mozilla/5.0',
             'https://legulegu.com/stockdata/market-activity'],
            capture_output=True, text=True, timeout=18
        )
        content = result.stdout

        mu = re.search(r'(\d+)家上涨', content)
        md = re.search(r'(\d+)家下跌', content)
        mz = re.search(r'(\d+)家涨停', content)
        mt = re.search(r'(\d+)家跌停', content)

        if mu and md:
            up = int(mu.group(1))   # ✅ group(1) 不是 group(2)
            down = int(md.group(1))  # ✅ group(1)
            zt = int(mz.group(1)) if mz else 0
            dt = int(mt.group(1)) if mt else 0
            return up, down, zt, dt

    except Exception as e:
        print(f"[legulegu] 获取失败: {e}")

    return -1, -1, -1, -1


def get_market_sentiment_tencent_fallback():
    """
    备源：腾讯行情接口采样估算（仅在legulegu失效时使用）
    """
    sample_codes = []

    for start in [600000, 600050, 600100, 600150, 600200, 600250, 600300, 600350,
                  600400, 600450, 600500, 600550, 600600, 600650, 600700, 600750,
                  600800, 600850, 600900, 600950, 601000, 601050, 601100, 601150,
                  601200, 601250, 601300, 601350, 601400, 601450, 601500, 601550,
                  601600, 601650, 601700, 601750, 601800, 601850]:
        for i in range(start, min(start + 100, 606000), 50):
            sample_codes.append(f"sh{i:06d}")

    for i in range(688000, 688700, 50):
        sample_codes.append(f"sh{i:06d}")

    for i in range(0, 4000, 50):
        sample_codes.append(f"sz{i:06d}")

    for i in range(300000, 303000, 50):
        sample_codes.append(f"sz{i:06d}")

    up = down = flat = total_checked = 0

    for i in range(0, len(sample_codes), 80):
        batch = sample_codes[i:i+80]
        query = ",".join(batch)
        try:
            url = f"https://qt.gtimg.cn/q={query}"
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            resp = urllib.request.urlopen(req, timeout=8)
            raw = resp.read().decode('gb2312', errors='replace')

            for line in raw.strip().split('\n'):
                if '~' not in line:
                    continue
                # 去掉前缀 v_sh600000="
                if '=' in line:
                    line = line.split('=', 1)[1]
                line = line.strip('"; ')
                if not line.startswith('"1~') and not line.startswith('"51~'):
                    continue
                parts = line.split('~')
                if len(parts) < 33:
                    continue
                try:
                    cp_str = parts[5] if parts[5] else ''
                    if not cp_str:
                        continue
                    change_pct = float(cp_str)
                    vol_str = parts[6] if len(parts) > 6 else ''
                    try:
                        volume = int(vol_str) if vol_str else 0
                    except:
                        volume = 0
                    # 停牌股过滤
                    if abs(change_pct) < 0.005 and volume == 0:
                        continue
                    total_checked += 1
                    if change_pct > 0:
                        up += 1
                    elif change_pct < 0:
                        down += 1
                    else:
                        flat += 1
                except (ValueError, TypeError):
                    pass
            if i + 80 < len(sample_codes):
                time.sleep(0.03)
        except Exception as e:
            print(f"批次{i//80+1}失败: {e}")
            continue

    if total_checked >= 50:
        ratio = 5500 / total_checked
        up_est = int(up * ratio)
        down_est = int(down * ratio)
        return up_est, down_est, 5500 - up_est - down_est, total_checked

    return 0, 0, 0, 0


def get_market_sentiment(use_cache=True):
    """获取涨跌家数"""
    if use_cache and os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE) as f:
                cache = json.load(f)
            age = time.time() - cache.get('timestamp', 0)
            if age < CACHE_TTL:
                print(f"[情绪] 缓存命中({cache.get('src','?')}), age={age:.0f}s")
                return cache['up'], cache['down'], cache.get('zt', 0), cache.get('dt', 0)
            else:
                print(f"[情绪] 缓存过期({age:.0f}s>{CACHE_TTL}s)，重新获取")
        except:
            pass

    print("[情绪] 获取主源 legulegu.com...")
    up, down, zt, dt = get_market_sentiment_legulegu()
    if up > 0 and down > 0:
        print(f"[情绪] legulegu: {up}涨/{down}跌 涨停{zt}跌停{dt}")
        cache_data = {'up': up, 'down': down, 'zt': zt, 'dt': dt,
                      'flat': 0, 'checked': up+down, 'timestamp': time.time(), 'src': 'legulegu'}
        try:
            with open(CACHE_FILE, 'w') as f:
                json.dump(cache_data, f)
        except:
            pass
        return up, down, zt, dt

    print("[情绪] 主源失败，启用腾讯采样...")
    up, down, flat, checked = get_market_sentiment_tencent_fallback()
    if up > 0 or down > 0:
        print(f"[情绪] 腾讯采样: {up}涨/{down}跌（采样{checked}只）")
        cache_data = {'up': up, 'down': down, 'flat': flat, 'checked': checked,
                      'timestamp': time.time(), 'src': 'tencent_sample'}
        try:
            with open(CACHE_FILE, 'w') as f:
                json.dump(cache_data, f)
        except:
            pass
        return up, down, flat, checked

    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE) as f:
                cache = json.load(f)
            print(f"[情绪] ⚠️ 所有数据源失败，使用过期缓存")
            return cache['up'], cache['down'], cache.get('flat', 0), cache.get('checked', 0)
        except:
            pass

    return 0, 0, 0, 0


def get_sentiment_legacy_format():
    """兼容旧接口格式"""
    up, down, flat, checked = get_market_sentiment()
    if up > 0 or down > 0:
        src = 'legulegu' if checked > 100 else 'tencent_sample'
        return {'up': up, 'down': down, 'zt': 0, 'dt': 0, 'src': src, 'checked': checked}
    return {'up': 0, 'down': 0, 'zt': 0, 'dt': 0, 'src': 'error'}


if __name__ == '__main__':
    print("=" * 40)
    print("涨跌家数获取测试（v3修复版）")
    print("=" * 40)

    print("\n[1] 直接获取 legulegu...")
    up, down, zt, dt = get_market_sentiment_legulegu()
    print(f"    结果: {up}涨/{down}跌 涨停{zt}跌停{dt}")

    print("\n[2] 完整流程...")
    up2, down2, flat2, checked2 = get_market_sentiment(use_cache=False)
    print(f"    估算: {up2}涨/{down2}跌（采样{checked2}只）")

    print("\n[3] 情绪判定:")
    if up2 > 0:
        if up2 >= 3500:
            phase = "极度高潮（辅助模式）"
        elif up2 >= 2500:
            phase = "高潮期（2.0+1.0主导）"
        elif up2 >= 2000:
            phase = "修复期（1.0+3.0）"
        elif up2 >= 1500:
            phase = "冰点修复（1.0主导，3.0熔断）"
        else:
            phase = "极度冰点（1.0主导）"
        print(f"    {up2}涨/{down2}跌 → {phase}")