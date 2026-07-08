#!/usr/bin/env python3
"""
龙虾3.0趋势池自动更新脚本 v2.1
数据源：腾讯历史K线(nofq=成交额+量纲正确) + 腾讯快照(总市值) + akshare(备用)

用法：
    python3 lobster_trend_pool_updater.py [--dry-run]
    python3 lobster_trend_pool_updater.py --verbose

v2.1 变更：
    1. 容量硬约束：5日均成交额≥10亿（原3亿）
    2. 新增市值过滤：总市值≥100亿（腾讯qt.gtimg.cn field ~44）
    3. 产业逻辑打分对齐 scoring_calculator.py 的 3.0_趋势低吸 模型：
       L1(🔴)=30分, L2(🟡)=20分, L3(🟢)=10分, L4=0分

流程：
    1. 解析产业逻辑框架.md → 赛道状态
    2. 遍历全部种子股（从 lobster-config.json 读取） → 获取MA + 成交额 + 市值
    3. 打分排序（产业30% + 均线25% + 成交额15% + 形态15% + 赛道15%）
    4. 入池/观察区/移出
    5. 写入趋势容量池.md
"""

import json, re, subprocess, sys, datetime, signal, concurrent.futures
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
import functools

# 全局超时控制（秒）
SCRIPT_TIMEOUT = 120  
REQUEST_TIMEOUT = 15  

def timeout_handler(signum, frame):
    print("\n⚠️ 脚本执行超时，强制退出")
    sys.exit(1)

# 设置全局超时
signal.signal(signal.SIGALRM, timeout_handler)
signal.alarm(SCRIPT_TIMEOUT)

WS = Path("/Users/yuefengshen/.qclaw/workspace-1gwpiwf3hr163jz5")
POOL_PATH = WS / "trading/趋势容量池.md"
FRAMEWORK_PATH = WS / "trading/产业逻辑框架.md"
CONFIG_PATH = WS / "lobster-config.json"

# ===== 从lobster-config.json加载种子股和约束（数据和逻辑分离） =====
def load_config():
    """加载配置，支持数据和逻辑分离"""
    try:
        with open(CONFIG_PATH) as f:
            cfg = json.load(f)
        tp = cfg.get("trend_pool", {})
        return {
            "stock_codes": tp.get("stock_codes", {}),
            "track_seeds": tp.get("seed_tracks", {}),
            "min_amount": tp.get("hard_constraints", {}).get("min_avg_amount", 10.0),
            "min_market_cap": tp.get("hard_constraints", {}).get("min_market_cap", 100.0),
            "min_score": tp.get("hard_constraints", {}).get("min_score", 35),
            "max_pool_size": tp.get("hard_constraints", {}).get("max_pool_size", 8),
        }
    except Exception as e:
        print(f"⚠️ 配置加载失败: {e}，使用默认值")
        return {
            "stock_codes": {},
            "track_seeds": {},
            "min_amount": 10.0,
            "min_market_cap": 100.0,
            "min_score": 35,
            "max_pool_size": 8,
        }

# 全局配置
CFG = load_config()
STOCK_CODE_MAP = CFG["stock_codes"]
TRACK_SEEDS = CFG["track_seeds"]
MIN_AMOUNT = CFG["min_amount"]
MIN_MARKET_CAP = CFG["min_market_cap"]
MIN_SCORE = CFG["min_score"]
MAX_POOL_SIZE = CFG["max_pool_size"]


def get_tencent_kline(code, days=25, fq="qfq"):
    """获取腾讯日K线（带超时控制）"""
    prefix = "sh" if code.startswith("6") else "sz"
    fq_param = "nofq" if fq == "nofq" else fq
    url = (f"https://web.ifzq.gtimg.cn/appstock/app/fqkline/get"
           f"?_var=kline_day{fq}&param={prefix}{code},day,,,{days},{fq_param}")
    try:
        r = subprocess.run(["curl", "-s", "--max-time", str(REQUEST_TIMEOUT), url], 
                           capture_output=True, text=True, timeout=REQUEST_TIMEOUT + 2)
        m = re.search(r"=\s*(\{.+)", r.stdout.strip())
        if not m: return None
        data = json.loads(m.group(1))
        key = f"{prefix}{code}"
        kdata = data["data"].get(key, {})
        for k in [fq + "day", fq, "day"]:
            if k in kdata:
                return kdata[k]
        return []
    except Exception as e:
        print(f"  ⚠️ K线获取失败 {code}: {e}")
        return None


def get_realtime_amount(code):
    """获取今日实时成交额（亿元）+ 总市值（亿）（带超时控制）"""
    prefix = "sh" if code.startswith("6") else "sz"
    url = f"https://qt.gtimg.cn/q={prefix}{code}"
    try:
        r = subprocess.run(["curl", "-s", "--max-time", str(REQUEST_TIMEOUT), url],
                           capture_output=True, timeout=REQUEST_TIMEOUT + 2)
        raw = r.stdout
        for enc in ["gb2312", "gbk", "utf-8", "latin1"]:
            try: txt = raw.decode(enc); break
            except: continue
        else:
            txt = raw.decode("utf-8", "replace")
        m = re.search(rf'v_{prefix}{code}="([^"]*)"', txt)
        if not m: return None, None
        parts = m.group(1).split("~")
        amt_wan = float(parts[37]) / 10000 if len(parts) > 37 else 0
        market_cap = float(parts[44]) if len(parts) > 44 else 0
        return amt_wan, market_cap
    except Exception as e:
        print(f"  ⚠️ 实时数据获取失败 {code}: {e}")
        return None, None


def calc_metrics(klines_qfq, klines_nofq):
    """计算MA + 成交额"""
    if not klines_qfq or len(klines_qfq) < 15:
        return None

    # MA用前复权数据
    closes_qfq = [float(k[2]) for k in klines_qfq]
    ma5  = sum(closes_qfq[-5:]) / 5
    ma10 = sum(closes_qfq[-10:]) / 10
    ma20 = sum(closes_qfq[-20:]) / 20 if len(closes_qfq) >= 20 else None
    last = closes_qfq[-1]

    # 成交额用nofq原始数据，公式：vol(手)*100*close(元)/1e8
    if klines_nofq and len(klines_nofq) >= 5:
        amt5 = sum(float(k[5]) * 100 * float(k[2]) for k in klines_nofq[-5:]) / 5 / 1e8
        amt10 = sum(float(k[5]) * 100 * float(k[2]) for k in klines_nofq[-10:]) / 10 / 1e8
    else:
        amt5 = amt10 = 0

    # 市值从实时快照获取（在main中填充）
    market_cap = None

    return {
        "ma5": round(ma5, 2), "ma10": round(ma10, 2), "ma20": round(ma20, 2) if ma20 else None,
        "last": last,
        "ma_ok": ma5 > ma10,
        "ma_full": ma5 > ma10 and (ma20 is None or ma10 > ma20),
        "amount_5avg": round(amt5, 2),
        "amount_10avg": round(amt10, 2),
        "market_cap": market_cap,
        "last_date": klines_qfq[-1][0] if klines_qfq else None,
    }


def get_track_status():
    """从产业逻辑框架解析赛道状态"""
    status_map = {}
    if not FRAMEWORK_PATH.exists(): return status_map
    content = FRAMEWORK_PATH.read_text(encoding="utf-8")
    lines = content.split("\n")
    for line in lines:
        for track in TRACK_SEEDS:
            if track in line:
                for emoji in ["🔴","🟡","🟢"]:
                    if emoji in line:
                        status_map[track] = emoji
                        break
    return status_map


def load_sector_map():
    """加载动态产业图谱，过热赛道降权"""
    GRAPH_JSON = WS / "trading/产业图谱.json"
    if not GRAPH_JSON.exists():
        print("  ⚠️ 产业图谱.json不存在，跳过热降权")
        return {}
    try:
        data = json.loads(GRAPH_JSON.read_text())
        sector_map = {}
        for name, info in data.get('sectors', {}).items():
            dev = info.get('pool_dev_ma10_median')
            heat = info.get('dynamic_heat', '🟢')
            warnings = info.get('warnings', [])
            sector_map[name] = {
                'dev_ma10': dev,
                'heat': heat,
                'warnings': warnings,
            }
        print(f"  产业图谱加载 {len(sector_map)} 个赛道")
        return sector_map
    except Exception as e:
        print(f"  ⚠️ 产业图谱加载失败: {e}")
        return {}



def score_candidate(c, track_status, sector_map=None):
    """打分：对齐 scoring_calculator.py 3.0_趋势低吸 模型

    产业逻辑强度 30%  → L1(🔴)=30, L2(🟡)=20, L3(🟢)=10, L4=0
    均线排列      25%  → 完整多头=25, 部分多头=15
    成交额(亿)    15%  → ≥30亿=15, ≥10亿=12, ≥5亿=8, ≥3亿=4
    位置形态      15%  → 回踩MA10<3%=15, 回踩MA20<3%=10
    赛道稀缺性    15%  → 🔴=15, 🟡=8, 🟢=5
    """
    score = 0
    status = track_status.get(c["track"], "")

    # 产业逻辑强度 30% — 对齐 scoring_calculator L1/L2/L3/L4
    s_map = {"🔴": 30, "🟡": 20, "🟢": 10}
    score += s_map.get(status, 0)

    # 均线状态 25%
    if c.get("ma_full"): score += 25
    elif c.get("ma_ok"): score += 15

    # 成交额 15%
    amt = c.get("amount_5avg", 0)
    if amt >= 30: score += 15
    elif amt >= 10: score += 12
    elif amt >= 5: score += 8
    elif amt >= 3: score += 4

    # 位置形态 15%
    last = float(c.get("last", 0))
    ma10 = c.get("ma10", 0)
    if ma10 and last > 0:
        dist_ma10 = abs(last - ma10) / ma10
        dist_ma20 = abs(last - c.get("ma20", ma10)) / c.get("ma20", ma10) if c.get("ma20") else 999
        if dist_ma10 < 0.03: score += 15
        elif dist_ma20 < 0.03: score += 10

    # 赛道稀缺性 15%
    if status == "🔴": score += 15
    elif status == "🟡": score += 8
    elif status == "🟢": score += 5

    # === 动态产业图谱过热降权（v2.2新增）===
    if sector_map:
        sm = sector_map.get(c['track'], {})
        dev = sm.get('dev_ma10')
        heat = sm.get('heat', '🟢')
        # 偏离MA10 > 10% → 过热降权
        if dev is not None and dev > 10:
            score = max(0, score - 30)
            print(f"    ⚠️ {c['name']}({c['track']}) 偏离+{dev:.1f}% → 降权30分 → {score}")
        elif dev is not None and dev > 5:
            score = max(0, score - 15)
            print(f"    ⚠️ {c['name']}({c['track']}) 偏离+{dev:.1f}% → 降权15分 → {score}")
        # 🟢回调到位加分
        if dev is not None and dev < 0 and dev > -5:
            score += 10
            print(f"    ✅ {c['name']}({c['track']}) 回调到位{dev:.1f}% → 加权10分 → {score}")

    return score


def main():
    verbose = "--verbose" in sys.argv or "-v" in sys.argv
    dry_run = "--dry-run" in sys.argv

    today = datetime.date.today().strftime("%Y-%m-%d")
    print(f"\n{'='*52}")
    print(f"🦞 3.0趋势池自动更新 v2.1 | {today}")
    print(f"{'='*52}")

    # 1. 读取框架获取赛道状态
    print("\n📋 步骤1：读取产业逻辑框架...")
    track_status = get_track_status()
    if track_status:
        print(f"  已解析 {len(track_status)} 个赛道状态")
    else:
        print("  ⚠️ 未解析到赛道状态，将扫描全部赛道")

    # 1.5 加载动态产业图谱（v2.2新增）
    print("\n📋 步骤1.5：加载动态产业图谱...")
    sector_map = load_sector_map()

    # 2. 遍历所有种子股获取数据（v2.1：增加市值 + 超时控制）
    print(f"\n📊 步骤2：遍历 {len(STOCK_CODE_MAP)} 只种子股（含市值过滤）...")
    print(f"  硬约束：5日均额≥{MIN_AMOUNT}亿 | 总市值≥{MIN_MARKET_CAP}亿")
    print(f"  单请求超时：{REQUEST_TIMEOUT}s | 总超时：{SCRIPT_TIMEOUT}s")
    
    all_candidates = []
    failed_stocks = []
    
    for name, code in STOCK_CODE_MAP.items():
        try:
            # 设置单只股票处理超时
            signal.alarm(REQUEST_TIMEOUT * 3)  # 3个请求 × 超时时间
            
            klines_qfq = get_tencent_kline(code, 25, "qfq")
            klines_nofq = get_tencent_kline(code, 10, "nofq")
            
            if not klines_qfq or len(klines_qfq) < 15:
                failed_stocks.append(f"{name}({code}): K线数据不足")
                signal.alarm(0)
                continue
            
            metrics = calc_metrics(klines_qfq, klines_nofq)
            if not metrics: 
                failed_stocks.append(f"{name}({code}): 指标计算失败")
                signal.alarm(0)
                continue
            
            # 获取实时成交额 + 总市值（腾讯快照）
            amt_today, market_cap = get_realtime_amount(code)
            metrics["market_cap"] = market_cap
            
            # 找赛道
            track = None
            for t, seeds in TRACK_SEEDS.items():
                if name in seeds: track = t; break
            if not track: track = "其他"
            
            c = {
                "name": name, "code": code, "track": track,
                "track_status": track_status.get(track, "🟡"),
                **metrics
            }
            all_candidates.append(c)
            signal.alarm(0)  # 清除超时
            
            if verbose:
                ok = "✅" if c["ma_ok"] else "❌"
                amt_ok = "✅" if c["amount_5avg"] >= MIN_AMOUNT else "❌"
                cap_ok = "✅" if (c.get("market_cap") or 0) >= MIN_MARKET_CAP else "❌"
                mc_str = f"市值{c['market_cap']}亿" if c.get("market_cap") else "市值N/A"
                print(f"  {c['track_status']}{ok}{amt_ok}{cap_ok} {name}({code}): "
                      f"MA5={c['ma5']} MA10={c['ma10']} "
                      f"5日均额={c['amount_5avg']}亿 {mc_str}")
                
        except Exception as e:
            failed_stocks.append(f"{name}({code}): {e}")
            signal.alarm(0)
            continue
    
    print(f"\n  数据采集完成：{len(all_candidates)} 只有效数据")
    if failed_stocks and verbose:
        print(f"  失败 {len(failed_stocks)} 只：")
        for f in failed_stocks[:5]: print(f"    - {f}")

    # 3. 打分排序
    print("\n🏆 步骤3：打分排序...")
    scored = []
    for c in all_candidates:
        c["score"] = score_candidate(c, track_status, sector_map)
        scored.append(c)
    scored.sort(key=lambda x: x["score"], reverse=True)

    if verbose:
        for i, c in enumerate(scored[:20]):
            amt_ok = "✅" if c["amount_5avg"] >= MIN_AMOUNT else "❌"
            cap_ok = "✅" if (c.get("market_cap") or 0) >= MIN_MARKET_CAP else "❌"
            ma_ok = "✅" if c["ma_ok"] else "❌"
            mc_str = f"市值{c['market_cap']}亿" if c.get("market_cap") else "市值N/A"
            print(f"  #{i+1:2d} [{c['score']:3d}分] {c['track_status']}{ma_ok}{amt_ok}{cap_ok} "
                  f"{c['name']}({c['code']}) {c['track']} "
                  f"MA5={c['ma5']}>{c['ma10']} 额={c['amount_5avg']}亿 {mc_str}")

    # 4. 分类：入池 / 观察区 / 移出
    pool, observe, removed = [], [], []

    for c in scored:
        # v2.1 入池条件：MA多头 + 成交额≥10亿 + 市值≥100亿 + 得分≥35
        mc = c.get("market_cap") or 0
        cond_pool = (c["ma_ok"]
                     and c["amount_5avg"] >= MIN_AMOUNT
                     and mc >= MIN_MARKET_CAP
                     and c["score"] >= MIN_SCORE)
        cond_observe = (c["ma_ok"] and c["score"] >= 20)

        if cond_pool:
            pool.append(c)
        elif cond_observe:
            observe.append(c)

    print(f"\n  入池候选：{len(pool)}只")
    print(f"  观察区：{len(observe)}只")

    # 5. 输出最终入池（最多8只）
    final_pool = pool[:8]
    print(f"\n✅ 最终入池：{len(final_pool)}只")
    for c in final_pool:
        print(f"  {c['track_status']} {c['name']}({c['code']}) "
              f"{c['track']} {c['score']}分 MA5={c['ma5']} 5日均额={c['amount_5avg']}亿")

    # 6. 写入文件
    content = build_pool_md(final_pool, observe, removed, scored, today)

    if dry_run:
        print(f"\n[DRY-RUN] 未写入文件")
    else:
        POOL_PATH.write_text(content, encoding="utf-8")
        print(f"\n💾 已写入：{POOL_PATH}")
        print(f"📄 {len(content)} 字节")

    # 7. 输出JSON供其他脚本使用
    result = {
        "date": today, "version": "v2.1",
        "pool_size": len(final_pool), "observe_size": len(observe),
        "total_scanned": len(all_candidates),
        "pool": [{
            "name": c["name"], "code": c["code"], "track": c["track"],
            "track_status": c["track_status"], "score": c["score"],
            "ma5": c["ma5"], "ma10": c["ma10"], "ma20": c["ma20"],
            "amount_5avg": c["amount_5avg"],
            "note": f"MA5={c['ma5']}>{c['ma10']}额{c['amount_5avg']}亿"
        } for c in final_pool],
        "observe": [{
            "name": c["name"], "code": c["code"], "track": c["track"],
            "score": c["score"], "reason": "均线多头但成交额不足" if c["amount_5avg"] < MIN_AMOUNT else "得分不足"
        } for c in observe[:10]],
    }
    update_path = ROOT / "trading" / "trend_pool_update.json"
    with open(update_path, "w") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"\n{'='*52}")
    print(f"✅ 完成：{len(final_pool)}只入池（总额{MIN_AMOUNT}亿+市值{MIN_MARKET_CAP}亿）| "
          f"共扫描{len(all_candidates)}只 | {today}")
    print(f"{'='*52}")


def build_pool_md(pool, observe, removed, all_scored, today):
    """生成趋势容量池.md内容"""
    lines = [
        "# 📊 趋势容量池（3.0维度）",
        "",
        f"> 维护规则：周日20:00进化任务自动更新 + 每日收盘复盘检查",
        f"> 创建日期：2026-05-14 | **最后更新：{today}（自动更新 v2.1）**",
        "> 数据源：腾讯日K线(nofq) + 腾讯实时快照",
        "> ⚠️ 注意：akshare K线接口不稳定，仅用腾讯接口",
        "",
        "---",
        "",
        "## 入池标准（3.0打分模型 v2.1）",
        "",
        "| 维度 | 指标 | 阈值 | 得分 |",
        "|-----|------|------|------|",
        "| 产业逻辑（30%） | 🔴超级短缺/短缺确认 | L1 | 30分 |",
        "| 产业逻辑（30%） | 🟡产能爬坡/鱼尾 | L2 | 20分 |",
        "| 产业逻辑（30%） | 🟢早期/转折 | L3 | 10分 |",
        "| 均线（25%） | MA5>MA10>MA20 | 完整多头 | 25分 |",
        "| 均线（25%） | MA5>MA10 | 部分多头 | 15分 |",
        "| 成交额（15%） | ≥30亿 | 超级容量 | 15分 |",
        "| 成交额（15%） | ≥10亿 | 大容量 | 12分 |",
        "| 成交额（15%） | ≥5亿 | 中容量 | 8分 |",
        "| 成交额（15%） | ≥3亿 | 入门 | 4分 |",
        "| 市值（新增硬约束） | 总市值≥100亿 | 容量安全 | 强制 |",
        "| 形态（15%） | 回踩MA10<3% | 买点 | 15分 |",
        "| 赛道（15%） | 🔴稀缺 | L1 | 15分 |",
        "| 赛道（15%） | 🟡爬坡 | L2 | 8分 |",
        "| 赛道（15%） | 🟢早期 | L3 | 5分 |",
        "",
        f"## 当前池中（{today}，共{len(pool)}只）",
        "",
        "| 标的 | 代码 | 赛道 | 赛道状态 | MA5 | MA10 | MA20 | "
        "5日均额(亿) | 总市值(亿) | 总分 | 入池理由 |",
        "|-----|------|------|----------|-----|------|------|"
        "----------------|-----------|------|----------|",
    ]

    for c in pool:
        ma_str = f"{c['ma5']}>{c['ma10']}"
        if c.get('ma20'): ma_str += f">{c['ma20']}"
        mc_str = f"{c['market_cap']:.0f}" if c.get("market_cap") else "-"
        lines.append(
            f"| {c['name']} | {c['code']} | {c['track']} | {c['track_status']} | "
            f"{c['ma5']} | {c['ma10']} | {c.get('ma20','-')} | "
            f"{c['amount_5avg']} | {mc_str} | {c['score']} | "
            f"✅均线多头+额{c['amount_5avg']}亿+市值{mc_str}亿 |"
        )

    if observe:
        lines += [
            "",
            f"## 观察区（{len(observe)}只，满足部分条件）",
            "",
            "| 标的 | 代码 | 赛道 | 得分 | 不满足条件 | 入池条件 |",
            "|-----|------|------|------|------------|----------|",
        ]
        for c in observe[:15]:
            reasons = []
            if not c.get("ma_ok"): reasons.append("均线未多头")
            if c.get("amount_5avg", 0) < MIN_AMOUNT: reasons.append(f"额{c['amount_5avg']}亿<{MIN_AMOUNT}亿")
            mc = c.get("market_cap") or 0
            if mc < MIN_MARKET_CAP: reasons.append(f"市值{mc:.0f}亿<{MIN_MARKET_CAP}亿")
            if c.get("score", 0) < MIN_SCORE: reasons.append(f"得分{c['score']}<{MIN_SCORE}")
            entry = "; ".join(reasons) if reasons else "待催化"
            lines.append(
                f"| {c['name']} | {c['code']} | {c['track']} | {c['score']} | "
                f"{entry} | {'; '.join(r for r in [('MA多头' if c.get('ma_ok') else ''), ('额≥10亿' if c.get('amount_5avg',0)>=MIN_AMOUNT else ''), ('市值≥100亿' if mc>=MIN_MARKET_CAP else '')] if r) or '综合催化'} |"
            )

    if removed:
        lines += [
            "",
            f"## 移出记录（{today}，{len(removed)}只）",
            "",
            "| 标的 | 代码 | 移出原因 |",
            "|-----|------|----------|",
        ]
        for c in removed:
            lines.append(f"| {c['name']} | {c['code']} | {c.get('reason','MA破位')} |")

    lines += [
        "",
        "## 买卖点规则（3.0专用）",
        "",
        "| 买点 | 条件 | 仓位（L1×L2矩阵） |",
        "|-----|------|------|",
        "| 情绪拐点低吸 | 880005连续2日>2500 + 回踩MA10/MA20 | 5-25%（矩阵） |",
        "| 趋势回调低吸 | 均线多头不变 + 回踩MA10不破 + 量缩 | 5-25%（矩阵） |",
        "| 突破确认追入 | 放量突破平台 + 回踩确认不破 | 5-25%（矩阵） |",
        "",
        "| 卖点 | 条件 | 操作 |",
        "|-----|------|------|",
        "| 均线破位 | MA5<MA10且3日内不收回 | 清仓 |",
        "| 逻辑证伪 | 产业趋势被明确证伪 | 清仓 |",
        "| 一致性高潮 | 赛道状态→🔴高潮边缘 | 减至1成 |",
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    main()