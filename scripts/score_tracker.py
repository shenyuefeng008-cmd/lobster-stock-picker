#!/usr/bin/env python3
"""
候选评分跟踪器 v2
在盘前引擎完成后运行：读取盘前candidates的score_detail → 追加到 score_history.json

数据流：
  盘前引擎(07:00) → 写 /tmp/lobster_premarket_candidates.json (含 score_detail)
  本脚本读该文件 → 追加到 trading/score_history.json（按 date+code 去重）
  进化分析器(00:10) → 读 score_history.json + 模拟持仓 → 算分项PnL → 调权重

调用方式：
  python3 score_tracker.py [date]
  默认用当天日期，也可指定 date=2026-05-25
"""

import json, sys, os, glob
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HISTORY_PATH = ROOT / "trading" / "score_history.json"
INPUT_PATH = "/tmp/lobster_premarket_candidates.json"

def load_history():
    if HISTORY_PATH.exists():
        try:
            return json.loads(HISTORY_PATH.read_text())
        except:
            pass
    return {"records": [], "meta": {"version": "2.0", "last_updated": "", "total_records": 0}}

def save_history(data):
    data["meta"]["last_updated"] = datetime.now().strftime("%Y-%m-%d %H:%M")
    data["meta"]["total_records"] = len(data["records"])
    HISTORY_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2))

def main():
    today = sys.argv[1] if len(sys.argv) > 1 else date.today().strftime("%Y-%m-%d")

    if not os.path.exists(INPUT_PATH):
        print(f"⚠️ 盘前候选文件不存在: {INPUT_PATH}")
        print("   可能原因：非交易时段或盘前引擎未运行")
        return

    try:
        data = json.loads(Path(INPUT_PATH).read_text())
    except Exception as e:
        print(f"⚠️ 读取盘前数据失败: {e}")
        return

    # 校验日期
    data_date = data.get("date", "")
    if isinstance(data_date, str) and data_date and data_date != today:
        print(f"⚠️ 日期不匹配: 文件={data_date}, 期望={today}")
        # 以文件日期为准
        today = data_date

    history = load_history()
    existing_codes = {(r["date"], r["code"]) for r in history["records"]}
    new_records = 0
    dim_labels = ["1.0一进二", "1.0分歧低吸", "2.0板块卡位", "3.0趋势低吸"]

    candidates = data.get("candidates", {})
    for dim in dim_labels:
        stocks = candidates.get(dim, [])
        for s in stocks:
            code = s.get("代码", "?")
            key = (today, code)
            if key in existing_codes:
                continue
            sd = s.get("score_detail", {})
            if not sd:
                continue  # 无分项数据，跳过
            record = {
                "date": today,
                "code": code,
                "name": s.get("名称", "?"),
                "dimension": dim,
                "total_score": sum(sd.values()),
                "score_detail": sd,
                "raw": {k: v for k, v in s.items() if k != "score_detail"}
            }
            history["records"].append(record)
            new_records += 1

    if new_records > 0:
        save_history(history)
        print(f"✅ 新增 {new_records} 条评分记录 (累计 {len(history['records'])} 条)")
    else:
        print(f"ℹ️ 无新记录 (当日已存在或无score_detail)")

    # 展示各维度记录数
    dim_counts = {}
    for r in history["records"]:
        d = r["dimension"]
        dim_counts[d] = dim_counts.get(d, 0) + 1
    for d, c in sorted(dim_counts.items()):
        print(f"  {d}: {c}条")


if __name__ == "__main__":
    main()
