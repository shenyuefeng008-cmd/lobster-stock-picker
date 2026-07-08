#!/usr/bin/env python3
"""
产业逻辑进化数据采集脚本 v3.0
核心改造：从 LLM 主观语义匹配 → 结构化、可追踪、代码驱动的硬流程

新增能力：
  a) 读取 sector_name_mapping.json，对今日涨停板块做 申万→框架 自动映射
  b) 输出 mapped_sectors：{框架赛道: 今日涨停数}
  c) 输出 unmapped_sectors：{申万板块: 今日涨停数} → 潜在新赛道候选
  d) 读取 candidate_sectors.json，对比今日/昨日 unmapped，生成 candidate_alerts
  e) 支持 --mock 模式，使用硬编码 mock 数据验证映射和候选检测逻辑

输出JSON（trading/industry_evolution_YYYYMMDD.json）：
  - sector_counts:    申万行业 → 涨停数（原始数据）
  - mapped_sectors:   框架赛道 → 今日涨停数（自动映射后）
  - unmapped_sectors: 未映射板块 → 今日涨停数
  - candidate_alerts: 新候选 / 升级信号
  - framework_text:   产业逻辑框架.md 全文
  - catalyst_db:      催化剂数据库.json 全文
  - unverified:       未验证催化剂列表
"""

import json, datetime, re, sys, os
from pathlib import Path

BASE = Path("/Users/yuefengshen/.qclaw/workspace-1gwpiwf3hr163jz5")
TRADING = BASE / "trading"
TODAY = datetime.date.today()
YESTERDAY = TODAY - datetime.timedelta(days=1)

MAPPING_FILE = TRADING / "sector_name_mapping.json"
CANDIDATE_FILE = TRADING / "candidate_sectors.json"


# ─────────────────────────────────────────────────────────────
# 工具函数
# ─────────────────────────────────────────────────────────────

def load_json(path, default=None):
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return default


def save_json(path, data):
    with open(path, "w") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def get_mock_sector_counts():
    """Mock 数据：模拟 2026-07-02 涨停池的申万行业分布"""
    return {
        "元件": 9,
        "半导体": 7,
        "通信设备": 5,
        "电网设备": 7,
        "通用设备": 3,
        "化学制品": 4,
        "工业金属": 6,
        "小金属": 3,
        "电子化学": 4,
        "光学光电": 5,
        "汽车零部": 4,
        "航空装备": 3,
        "玻璃玻纤": 5,
        "其他电子": 5,
        "IT服务Ⅱ": 3,
        "化学原料": 2,
        "农化制品": 2,
        "塑料": 1,
        "专用设备": 2,
    }


def get_mock_yesterday_unmapped():
    """Mock 昨日 unmapped 数据（用于验证候选检测）"""
    return {
        "玻璃玻纤": 5,
        "其他电子": 5,
    }


# ─────────────────────────────────────────────────────────────
# Step 1：获取涨停池
# ─────────────────────────────────────────────────────────────

def fetch_zt_sector_counts(use_mock=False):
    """获取涨停池，按申万行业统计。返回 {行业名: 涨停数}。"""
    if use_mock:
        print("  ℹ️ 使用 Mock 数据（--mock 模式）")
        return get_mock_sector_counts()

    # 优先读本地缓存文件
    for d in (TODAY, YESTERDAY):
        sector_file = str(TRADING / f"sector_limit_up_{d.strftime('%Y%m%d')}.json")
        data = load_json(sector_file)
        if data and data.get("sector_counts"):
            print(f"  ✅ 读取本地缓存：{sector_file}")
            return data["sector_counts"]

    # fallback: akshare
    print("  ⚠️ 本地缓存不存在，尝试 akshare 获取...")
    try:
        import akshare as ak
        date_str = YESTERDAY.strftime("%Y%m%d")
        df = ak.stock_zt_pool_em(date=date_str)
        sector_count = {}
        for _, row in df.iterrows():
            sec = str(row.get("所属行业", row.get("industry", "未知")))
            sector_count[sec] = sector_count.get(sec, 0) + 1
        print(f"  ✅ akshare 获取涨停池 {date_str}：{len(df)} 只")
        return sector_count
    except Exception as e:
        print(f"  🔴 akshare 获取失败: {e}")
        return {}


# ─────────────────────────────────────────────────────────────
# Step 2：加载映射表，执行 申万→框架 映射
# ─────────────────────────────────────────────────────────────

def load_sector_mapping():
    """
    读取 sector_name_mapping.json，返回：
      - forward:  {框架赛道: [别名列表]}  （框架→别名）
      - reverse:  {申万行业: 框架赛道}    （申万→框架）
    """
    data = load_json(MAPPING_FILE)
    if not data:
        print(f"  🔴 映射文件不存在：{MAPPING_FILE}，跳过映射")
        return {}, {}

    forward = data.get("框架→别名", {})
    reverse = data.get("申万→框架", {})
    print(f"  ✅ 映射表加载：正向 {len(forward)} 条，反向 {len(reverse)} 条")
    return forward, reverse


def map_sectors(sector_counts, reverse_mapping):
    """
    将申万行业涨停统计映射到框架赛道。
    返回：
      mapped:   {框架赛道: 涨停数}
      unmapped: {申万行业: 涨停数}（未命中反向映射的）
    """
    mapped = {}
    unmapped = {}

    for sw_sector, count in sector_counts.items():
        framework_name = reverse_mapping.get(sw_sector)
        if framework_name:
            mapped[framework_name] = mapped.get(framework_name, 0) + count
        else:
            unmapped[sw_sector] = count

    return mapped, unmapped


# ─────────────────────────────────────────────────────────────
# Step 3：候选赛道检测（对比今日/昨日 unmapped）
# ─────────────────────────────────────────────────────────────

def load_candidate_db():
    """读取 candidate_sectors.json，返回 candidates 列表。"""
    data = load_json(CANDIDATE_FILE, {"candidates": [], "version": "1.0"})
    return data


def save_candidate_db(data):
    data["last_updated"] = TODAY.isoformat()
    save_json(CANDIDATE_FILE, data)


def detect_candidates(today_unmapped, candidate_db, use_mock=False):
    """
    对比今日 unmapped 板块与候选跟踪库，生成 alerts。
    返回：
      new_candidates:  [{name, zt_count, status: "first_seen"}]
      upgrade_signals: [{name, zt_count_today, zt_count_yesterday, status}]
    """
    new_candidates = []
    upgrade_signals = []

    # 读取昨日 unmapped（mock 模式用 mock 数据）
    yesterday_unmapped = {}
    if use_mock:
        yesterday_unmapped = get_mock_yesterday_unmapped()
    else:
        # 尝试读取昨日的 evolver 输出
        yest_json = str(TRADING / f"industry_evolution_{YESTERDAY.strftime('%Y%m%d')}.json")
        yest_data = load_json(yest_json)
        if yest_data:
            yesterday_unmapped = yest_data.get("unmapped_sectors", {})

    existing_names = {c["name"] for c in candidate_db.get("candidates", [])}

    for sector, count in today_unmapped.items():
        # 涨停数 < 3 的不视为有效候选
        if count < 3:
            continue

        yest_count = yesterday_unmapped.get(sector)

        if yest_count is not None and yest_count >= 3:
            # 昨日已在 unmapped 中且 ≥3 家 → 升级信号
            upgrade_signals.append({
                "name": sector,
                "zt_count_today": count,
                "zt_count_yesterday": yest_count,
                "status": "连续2日确认",
            })
        elif sector not in existing_names:
            # 今日新出现 → 新候选
            new_candidates.append({
                "name": sector,
                "zt_count": count,
                "status": "first_seen",
            })

    return new_candidates, upgrade_signals


def update_candidate_db(candidate_db, new_candidates, upgrade_signals, today_unmapped):
    """
    根据今日检测结果，更新 candidate_sectors.json。
    - 新候选：追加到 candidates 列表
    - 升级信号：更新对应条目的 zt_days，标记 upgrade_ready
    - 已淘汰且超过 30 天：可重新进入观察
    """
    candidates = candidate_db.get("candidates", [])
    existing = {c["name"]: c for c in candidates}

    # 更新/追加新候选
    for nc in new_candidates:
        name = nc["name"]
        if name in existing:
            # 已存在（可能是"已淘汰"状态），检查是否超过 30 天
            c = existing[name]
            if c["status"] == "已淘汰":
                last_date = datetime.date.fromisoformat(c.get("last_seen", "2000-01-01"))
                if (TODAY - last_date).days > 30:
                    c["status"] = "观察中"
                    c["zt_days"].append({"date": TODAY.isoformat(), "count": nc["zt_count"]})
                    c.pop("last_seen", None)
                    print(f"  ♻️  重新进入观察：{name}")
                else:
                    c["last_seen"] = TODAY.isoformat()
            else:
                # 观察中但未触发升级（可能昨天没数据）→ 追加今日记录
                c["zt_days"].append({"date": TODAY.isoformat(), "count": nc["zt_count"]})
        else:
            candidates.append({
                "name": name,
                "first_seen": TODAY.isoformat(),
                "zt_days": [{"date": TODAY.isoformat(), "count": nc["zt_count"]}],
                "status": "观察中",
            })
            existing[name] = candidates[-1]
            print(f"  🆕 新候选赛道：{name}（{nc['zt_count']} 家涨停）")

    # 处理升级信号
    for us in upgrade_signals:
        name = us["name"]
        if name in existing:
            c = existing[name]
            c["zt_days"].append({"date": TODAY.isoformat(), "count": us["zt_count_today"]})
            c["upgrade_ready"] = True
            print(f"  ⬆️  升级信号：{name}（今日 {us['zt_count_today']} 家，昨日 {us['zt_count_yesterday']} 家）")

    candidate_db["candidates"] = candidates
    return candidate_db


# ─────────────────────────────────────────────────────────────
# Step 4：读取框架文件和催化剂数据库
# ─────────────────────────────────────────────────────────────

def load_framework_and_catalysts():
    framework_path = TRADING / "产业逻辑框架.md"
    framework_text = ""
    if framework_path.exists():
        with open(framework_path) as f:
            framework_text = f.read()
        print(f"  ✅ 产业逻辑框架.md：{len(framework_text)} 字符")
    else:
        print(f"  🔴 文件不存在：{framework_path}")

    cat_db_path = TRADING / "催化剂数据库.json"
    cat_db = load_json(cat_db_path, {"catalysts": []})
    catalysts = cat_db.get("catalysts", [])
    unverified = [c for c in catalysts if not c.get("verified")]
    print(f"  催化剂总数：{len(catalysts)}，未验证：{len(unverified)}")

    return framework_text, cat_db, unverified


# ─────────────────────────────────────────────────────────────
# 主流程
# ─────────────────────────────────────────────────────────────

def main():
    use_mock = "--mock" in sys.argv

    print("=== 产业逻辑进化数据采集 v3.0 ===")
    print(f"日期：{TODAY.isoformat()}\n")

    # Step 1：获取涨停池
    print("[Step 1] 获取涨停池，按申万行业统计...")
    sector_counts = fetch_zt_sector_counts(use_mock=use_mock)
    if sector_counts:
        print(f"  申万行业涨停统计（Top10）：")
        for s, c in sorted(sector_counts.items(), key=lambda x: -x[1])[:10]:
            print(f"    {s}: {c} 家涨停")
        print(f"  合计：{sum(sector_counts.values())} 只涨停\n")
    else:
        print("  🔴 无涨停数据，退出\n")
        return

    # Step 2：加载映射表，执行映射
    print("[Step 2] 加载板块名称映射表，执行 申万→框架 映射...")
    _, reverse_mapping = load_sector_mapping()
    mapped_sectors, unmapped_sectors = map_sectors(sector_counts, reverse_mapping)

    print(f"  映射成功：{len(mapped_sectors)} 个框架赛道")
    for s, c in sorted(mapped_sectors.items(), key=lambda x: -x[1]):
        print(f"    {s}: {c} 家涨停")
    print(f"  未映射（候选）：{len(unmapped_sectors)} 个板块")
    for s, c in sorted(unmapped_sectors.items(), key=lambda x: -x[1]):
        print(f"    {s}: {c} 家涨停")
    print()

    # Step 3：候选赛道检测
    print("[Step 3] 候选赛道检测（对比今日/昨日 unmapped）...")
    candidate_db = load_candidate_db()
    new_candidates, upgrade_signals = detect_candidates(
        unmapped_sectors, candidate_db, use_mock=use_mock
    )

    print(f"  新候选：{len(new_candidates)} 个")
    for nc in new_candidates:
        print(f"    - {nc['name']}: {nc['zt_count']} 家涨停（{nc['status']}）")
    print(f"  升级信号：{len(upgrade_signals)} 个")
    for us in upgrade_signals:
        print(f"    - {us['name']}: 今日 {us['zt_count_today']} 家，"
              f"昨日 {us['zt_count_yesterday']} 家（{us['status']}）")
    print()

    # 更新 candidate_sectors.json
    print("[Step 3b] 更新 candidate_sectors.json...")
    candidate_db = update_candidate_db(candidate_db, new_candidates, upgrade_signals, unmapped_sectors)
    save_candidate_db(candidate_db)
    print(f"  ✅ 候选跟踪库已更新：{CANDIDATE_FILE}\n")

    # Step 4：读取框架文件和催化剂数据库
    print("[Step 4] 读取产业逻辑框架.md 和催化剂数据库...")
    framework_text, cat_db, unverified = load_framework_and_catalysts()
    print()

    # Step 5：输出结果 JSON
    print("[Step 5] 输出结果 JSON...")
    output = {
        "date": TODAY.isoformat(),
        "sector_counts": sector_counts,
        "mapped_sectors": mapped_sectors,
        "unmapped_sectors": unmapped_sectors,
        "candidate_alerts": {
            "new_candidates": new_candidates,
            "upgrade_signals": upgrade_signals,
        },
        "framework_text": framework_text,
        "catalyst_db": cat_db,
        "unverified_catalysts": [
            {"id": c.get("id"), "sector": c.get("sector"), "date": c.get("date"), "type": c.get("type")}
            for c in unverified
        ],
    }

    output_path = str(TRADING / f"industry_evolution_{TODAY.strftime('%Y%m%d')}.json")
    save_json(output_path, output)
    print(f"  ✅ 输出：{output_path}\n")

    print("=" * 60)
    print("✅ 数据采集完成")
    print(f"  - 映射成功：{len(mapped_sectors)} 个框架赛道")
    print(f"  - 未映射：{len(unmapped_sectors)} 个板块")
    print(f"  - 新候选：{len(new_candidates)} 个")
    print(f"  - 升级信号：{len(upgrade_signals)} 个")
    print("=" * 60)


if __name__ == "__main__":
    main()
