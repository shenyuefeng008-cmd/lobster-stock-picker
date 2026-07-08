#!/usr/bin/env python3
"""
涨跌家数获取脚本 - v7（华泰为主源，多源降级保活）
主源：华泰 marketInsight（HTSC skill）
降级1：腾讯行情接口采样估算
降级2：legulegu.com
降级3：新浪财经分页统计
"""

import urllib.request
import time
import json
import os
import subprocess
import re

from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
CACHE_FILE = str(ROOT / 'trading' / 'sentiment_cache.json')
CACHE_TTL = 1800  # 30分钟缓存（与盘中巡检间隔对齐）


def get_market_sentiment_htsc():
    """
    主源：华泰 marketInsight（HTSC skill）
    调用 financial_analysis skill 的 marketInsight 接口获取实时涨跌家数
    """
    try:
        import sys as _sys
        # 加载华泰 API key
        htsc_config = os.path.expanduser('~/.htsc-skills/config')
        if os.path.exists(htsc_config):
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
        ], capture_output=True, text=True, timeout=30,
           cwd=_FIN_ANALYSIS)
        out = r.stdout + r.stderr
        mu = re.search(r'上涨[：:\s]*(\d+)\s*家', out)
        md = re.search(r'下跌[：:\s]*(\d+)\s*家', out)
        mz = re.search(r'涨停[：:\s]*(\d+)\s*家', out)
        mt = re.search(r'跌停[：:\s]*(\d+)\s*家', out)
        up = int(mu.group(1)) if mu else 0
        down = int(md.group(1)) if md else 0
        zt = int(mz.group(1)) if mz else 0
        dt = int(mt.group(1)) if mt else 0
        if up > 0 and down > 0:
            total = up + down
            flat_est = 5500 - total if total < 5500 else 0
            return up, down, zt, dt, flat_est, total
    except Exception as e:
        print(f"华泰marketInsight失败: {e}")
    return 0, 0, 0, 0, 0, 0


def get_market_sentiment_sina():
    """
    主源：新浪财经分页统计（均匀采样）
    取前5页（500只）统计涨跌家数，按全市场5500只估算
    """
    try:
        ups = downs = zts = dts = total_checked = 0
        import urllib.request as _ur
        import json as _json
        # 取前5页（500只），提高采样覆盖
        for pg in [1, 2, 3, 4, 5]:
            u = f"https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/Market_Center.getHQNodeData?page={pg}&num=100&sort=code&asc=1&node=hs_a"
            req = _ur.Request(u, headers={"User-Agent": "Mozilla/5.0"})
            with _ur.urlopen(req, timeout=8) as resp:
                raw = resp.read()
                # 尝试解码
                for enc in ['gbk', 'gb2312', 'utf-8']:
                    try:
                        items = _json.loads(raw.decode(enc))
                        break
                    except:
                        items = []
                if not items:
                    continue
                for i in items:
                    try:
                        cp = float(i.get('changepercent', 0))
                        if cp > 0: ups += 1
                        elif cp < 0: downs += 1
                        if cp >= 9.8: zts += 1
                        elif cp <= -9.8: dts += 1
                        total_checked += 1
                    except: pass
        if total_checked >= 50:
            # 新浪采样500只，全市场约5500只，放大系数约11倍
            ratio = 5500 / max(total_checked, 1)
            up_est = int(ups * ratio)
            down_est = int(downs * ratio)
            flat_est = 5500 - up_est - down_est
            return up_est, down_est, zts, dts, flat_est, total_checked
    except Exception as e:
        print(f"新浪获取失败: {e}")
    return 0, 0, 0, 0, 0, 0


def get_market_sentiment_tencent():
    """
    降级源：腾讯行情接口采样估算
    采样约800只股票（上证+深证+创业板+科创板），按涨跌幅统计后按比例放大
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
        return up_est, down_est, 0, 0, 5500 - up_est - down_est, total_checked

    return 0, 0, 0, 0, 0, 0


def get_market_sentiment_legulegu():
    """
    降级源2：legulegu.com 全市场统计
    """
    try:
        r = subprocess.run(["curl", "-s", "-L", "--max-time", "10", "-A", "Mozilla/5.0",
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
            total = up + down
            flat_est = 5500 - total if total < 5500 else 0
            return up, down, zt, dt, flat_est, total
    except Exception as e:
        print(f"legulegu获取失败: {e}")
    return 0, 0, 0, 0, 0, 0


def get_market_sentiment(use_cache=True):
    """获取涨跌家数（华泰为主源，多源降级保活）"""
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

    # 主源：华泰 marketInsight（HTSC skill）
    print("[情绪] 主源：华泰marketInsight...")
    up, down, zt, dt, flat, checked = get_market_sentiment_htsc()
    if up > 0 and down > 0:
        print(f"[情绪] 华泰: {up}涨/{down}跌 涨停{zt}跌停{dt}")
        cache_data = {'up': up, 'down': down, 'zt': zt, 'dt': dt,
                      'flat': flat, 'checked': checked,
                      'timestamp': time.time(), 'src': 'htsc'}
        try:
            with open(CACHE_FILE, 'w') as f:
                json.dump(cache_data, f)
        except:
            pass
        return up, down, zt, dt

    # 降级1：腾讯采样
    print("[情绪] 华泰失败，降级腾讯采样...")
    up2, down2, flat2, checked2, _, _ = get_market_sentiment_tencent()
    if up2 > 0 or down2 > 0:
        print(f"[情绪] 腾讯采样: {up2}涨/{down2}跌（采样{checked2}只）")
        cache_data = {'up': up2, 'down': down2, 'flat': flat2, 'checked': checked2,
                      'timestamp': time.time(), 'src': 'tencent_sample'}
        try:
            with open(CACHE_FILE, 'w') as f:
                json.dump(cache_data, f)
        except:
            pass
        return up2, down2, 0, 0

    # 降级2：legulegu.com
    print("[情绪] 腾讯失败，降级legulegu...")
    up3, down3, zt3, dt3, flat3, checked3 = get_market_sentiment_legulegu()
    if up3 > 0 or down3 > 0:
        print(f"[情绪] legulegu: {up3}涨/{down3}跌 涨停{zt3}跌停{dt3}")
        cache_data = {'up': up3, 'down': down3, 'zt': zt3, 'dt': dt3,
                      'flat': flat3, 'checked': checked3,
                      'timestamp': time.time(), 'src': 'legulegu'}
        try:
            with open(CACHE_FILE, 'w') as f:
                json.dump(cache_data, f)
        except:
            pass
        return up3, down3, zt3, dt3

    # 降级3：新浪财经采样
    print("[情绪] legulegu失败，降级新浪采样...")
    up4, down4, zt4, dt4, flat4, checked4 = get_market_sentiment_sina()
    if up4 > 0 or down4 > 0:
        print(f"[情绪] 新浪采样: {up4}涨/{down4}跌 涨停{zt4}跌停{dt4}（采样{checked4}只）")
        cache_data = {'up': up4, 'down': down4, 'zt': zt4, 'dt': dt4,
                      'flat': flat4, 'checked': checked4,
                      'timestamp': time.time(), 'src': 'sina'}
        try:
            with open(CACHE_FILE, 'w') as f:
                json.dump(cache_data, f)
        except:
            pass
        return up4, down4, zt4, dt4

    # 兜底：读取过期缓存
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE) as f:
                cache = json.load(f)
            print(f"[情绪] ⚠️ 所有数据源失败，使用过期缓存({cache.get('src','?')})")
            return cache['up'], cache['down'], cache.get('flat', 0), cache.get('checked', 0)
        except:
            pass

    return 0, 0, 0, 0


def get_sentiment_legacy_format():
    """兼容旧接口格式"""
    up, down, zt, dt = get_market_sentiment()
    if up > 0 or down > 0:
        return {'up': up, 'down': down, 'zt': zt, 'dt': dt, 'src': 'htsc', 'checked': 0}
    return {'up': 0, 'down': 0, 'zt': 0, 'dt': 0, 'src': 'error'}


if __name__ == '__main__':
    print("=" * 40)
    print("涨跌家数获取测试（v7 华泰为主源）")
    print("=" * 40)

    print("\n[1] 完整流程（跳过缓存）...")
    up2, down2, zt2, dt2 = get_market_sentiment(use_cache=False)
    print(f"    结果: {up2}涨/{down2}跌 涨停{zt2}跌停{dt2}")

    print("\n[2] 情绪判定:")
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
