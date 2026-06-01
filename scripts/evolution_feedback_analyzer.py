#!/usr/bin/env python3
"""
进化反馈分析器 v2 — 自动调参版
读交易数据 → 直接改 config → 更新 feedback.json

修改 lobster-config.json 的规则：
  维度胜率<40% ≥3笔 → 收紧(top_n-1 / score_per_zt+3)
  维度胜率>70% ≥3笔 → 放宽(top_n+1)
  维度亏损>2% → 收紧止损1%/仓位降档
"""

import json, datetime, sys, os
from pathlib import Path
from copy import deepcopy

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "lobster-config.json"

def load_json(path):
    try:
        with open(path) as f:
            return json.load(f)
    except Exception as e:
        print(f"  ⚠️ 读取失败 {path.name}: {e}", file=sys.stderr)
        return {}

def dump_json(data, path):
    with open(path, 'w') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# ── 维度 → config路径映射 ──
DIM_CONFIG_MAP = {
    "1.0": {"top_n_path": ["1.0_first_to_second", "top_n"],
            "score_path": ["1.0_first_to_second", "score_small_amount", "le_5000"],
            "pos_limit_path": ["emotion"],
            "label": "1.0一进二"},
    "2.0": {"top_n_path": ["2.0_sector", "top_n"],
            "score_path": ["2.0_sector", "score_per_zt"],
            "pos_limit_path": ["emotion", "2500_3500", "pos_limit"],
            "label": "2.0板块卡位"},
}


def get_config_value(config, path):
    """按路径列表读取配置"""
    v = config
    for k in path:
        if isinstance(v, dict) and k in v:
            v = v[k]
        else:
            return None
    return v


def set_config_value(config, path, value):
    """按路径列表写入配置（原地修改）"""
    v = config
    for k in path[:-1]:
        if k not in v or not isinstance(v[k], dict):
            v[k] = {}
        v = v[k]
    if path[-1] in v and v[path[-1]] != value:
        old_val = v[path[-1]]
        v[path[-1]] = value
        return True, old_val
    v[path[-1]] = value
    return False, None


def analyze_trades(trade_log):
    """分析已平仓交易"""
    closed = [t for t in trade_log if t.get('pnl_pct') is not None]
    if not closed:
        return {"total": 0, "by_dimension": {}, "by_sell_type": {}}

    by_dim = {}
    for t in closed:
        dim_key = t.get('dimension', '未知').split('-')[0].strip()
        by_dim.setdefault(dim_key, []).append(t)

    result = {
        "total": len(closed),
        "wins": len([t for t in closed if t['pnl_pct'] > 0]),
        "win_rate": round(len([t for t in closed if t['pnl_pct'] > 0])/len(closed)*100, 1) if closed else 0,
        "total_pnl_pct": round(sum(t['pnl_pct'] for t in closed), 2),
        "avg_pnl_pct": round(sum(t['pnl_pct'] for t in closed)/len(closed), 2) if closed else 0,
        "by_dimension": {}
    }

    for dim, trades in by_dim.items():
        dim_wins = [t for t in trades if t['pnl_pct'] > 0]
        dim_pnl = sum(t['pnl_pct'] for t in trades)
        result["by_dimension"][dim] = {
            "count": len(trades),
            "wins": len(dim_wins),
            "win_rate": round(len(dim_wins)/len(trades)*100, 1),
            "total_pnl_pct": round(dim_pnl, 2),
            "avg_pnl_pct": round(dim_pnl/len(trades), 2)
        }

    return result


def analyze_catalyst_db(catalyst_db):
    """分析催化剂验证结果"""
    catalysts = catalyst_db.get('catalysts', [])
    verified = [c for c in catalysts if c.get('verified')]
    if not verified:
        return {"total_verified": 0, "total_catalysts": len(catalysts)}
    outcomes = {}
    for c in verified:
        o = c.get('outcome', '未知')
        outcomes.setdefault(o, 0)
        outcomes[o] += 1
    return {
        "total_verified": len(verified),
        "total_catalysts": len(catalysts),
        "outcomes": outcomes
    }


def analyze_errors(error_db):
    """分析交易错误"""
    errors = error_db.get('errors', [])
    if not errors:
        return {"total": 0}
    by_reason = {}
    loss = 0
    for e in errors:
        r = e.get('reason', '未知').split('，')[0][:30]
        by_reason[r] = by_reason.get(r, 0) + 1
        loss += abs(e.get('loss_pct', 0))
    return {"total": len(errors), "total_loss_pct": round(loss, 2), "by_reason": by_reason}


def _already_adjusted_today(param_key):
    """检查 feedback.json 今天是否已经调整过该参数"""
    try:
        fb = json.loads((ROOT / "trading" / "feedback.json").read_text())
        today = datetime.date.today().isoformat()
        for entry in fb.get("parameter_evolution", {}).get("adjustment_history", []):
            if entry.get("date") != today:
                continue
            for a in entry.get("applied", []):
                if a.get("target", "").startswith(param_key):
                    return True
    except:
        pass
    return False


def _link_trades_to_factors(trade_log):
    """读取 score_history.json，将每笔平仓交易关联到其分项得分"""
    score_path = ROOT / "trading" / "score_history.json"
    if not score_path.exists():
        return []
    try:
        scores = json.loads(score_path.read_text())
        score_map = {(r["date"], r["code"]): r for r in scores.get("records", [])}
    except:
        return []
    
    closed = [t for t in trade_log if t.get('pnl_pct') is not None]
    linked = []
    for t in closed:
        date_str = t.get("date", "")[:10].replace("-", "")
        code = t.get("code", "")
        rec = score_map.get((date_str, code))
        if rec:
            # Normalize to factors list (support both factors[] and score_detail{})
            raw_factors = rec.get("factors") or []
            if not raw_factors:
                sd = rec.get("score_detail", {})
                # score_detail is a dict like {"额得分": 20, "板块强度得分": 15}
                for fname, fscore in sd.items():
                    raw_factors.append({"name": fname, "raw_value": fscore, "sub_score": fscore, "weight": 1.0, "weighted": fscore})
            linked.append({
                "code": code,
                "name": t.get("name", ""),
                "dimension": t.get("dimension", ""),
                "pnl_pct": t["pnl_pct"],
                "total_score": rec.get("total_score", 0),
                "factors": raw_factors
            })
    return linked


def _adjust_factor_weights(linked_trades, config):
    """基于分项得分 vs PnL 调整评分权重"""
    if len(linked_trades) < 3:
        return []
    
    by_dim = {}
    for lt in linked_trades:
        dim_key = lt.get("dimension", "未知").split("-")[0].strip()
        by_dim.setdefault(dim_key, []).append(lt)
    
    dim_map = {"1.0": "1.0_一进二", "2.0": "2.0_板块卡位", "3.0": "3.0_趋势低吸"}
    changes = []
    
    for dim_key, trades in by_dim.items():
        if len(trades) < 3:
            continue
        
        # 收集因子
        all_factors = {}
        for t in trades:
            for f in t.get("factors", []):
                all_factors.setdefault(f["name"], {"wins_score": [], "losses_score": [], "weights": []})
        
        for t in trades:
            is_win = t["pnl_pct"] > 0
            for f in t.get("factors", []):
                fn = f["name"]
                if fn in all_factors:
                    all_factors[fn]["weights"].append(f["weight"])
                    if is_win:
                        all_factors[fn]["wins_score"].append(f["weighted"])
                    else:
                        all_factors[fn]["losses_score"].append(f["weighted"])
        
        section = dim_map.get(dim_key)
        if not section:
            continue
        
        for fname, data in all_factors.items():
            wins_avg = sum(data["wins_score"]) / len(data["wins_score"]) if data["wins_score"] else 0
            losses_avg = sum(data["losses_score"]) / len(data["losses_score"]) if data["losses_score"] else 0
            diff = wins_avg - losses_avg
            total_n = len(data["wins_score"]) + len(data["losses_score"])
            if total_n < 3:
                continue
            
            cur_w = data["weights"][0] if data["weights"] else 0.15
            
            if diff > 3:
                new_w = round(min(cur_w * 1.15, 0.4), 2)
                if new_w > cur_w + 0.01:
                    changes.append({"factor": fname, "dim": dim_key,
                                    "diff": round(diff, 1), "weight": f"{cur_w}->{new_w}",
                                    "action": "增加 (胜者得分更高)"})
                    for ind in config.get("scoring_models", {}).get(section, {}).get("指标", []):
                        if ind.get("name") == fname:
                            ind["weight"] = new_w
            elif diff < -1:
                new_w = round(max(cur_w * 0.85, 0.05), 2)
                if new_w < cur_w - 0.01:
                    changes.append({"factor": fname, "dim": dim_key,
                                    "diff": round(diff, 1), "weight": f"{cur_w}->{new_w}",
                                    "action": "降低 (败者得分更高)"})
                    for ind in config.get("scoring_models", {}).get(section, {}).get("指标", []):
                        if ind.get("name") == fname:
                            ind["weight"] = new_w
            elif abs(diff) < 0.5:
                new_w = round(max(cur_w * 0.98, 0.05), 2)
                if abs(new_w - cur_w) > 0.005:
                    changes.append({"factor": fname, "dim": dim_key,
                                    "diff": round(diff, 1), "weight": f"{cur_w}->{new_w}",
                                    "action": "微降 (无区分度)"})
                    for ind in config.get("scoring_models", {}).get(section, {}).get("指标", []):
                        if ind.get("name") == fname:
                            ind["weight"] = new_w
    
    return changes


def apply_config_adjustments(trade_analysis, trade_log, config):

    changes = []
    dim_stats = trade_analysis.get("by_dimension", {})

    for dim, cfg_map in DIM_CONFIG_MAP.items():
        stats = dim_stats.get(dim)
        if not stats or stats["count"] < 3:
            continue

        wr = stats["win_rate"]
        avg_pnl = stats["avg_pnl_pct"]
        label = cfg_map["label"]

        # ── 胜率<40% → 收紧 ──
        if wr < 40:
            # 每日只调一次
            if _already_adjusted_today(label):
                print(f"    已调过 {label}，跳过（每日限1次）")
                continue
            # 先降 top_n（不可低于2）
            cur_top = get_config_value(config, cfg_map["top_n_path"])
            if cur_top is not None and cur_top >= 3:
                changed, old = set_config_value(config, cfg_map["top_n_path"], cur_top - 1)
                if changed:
                    changes.append(f"{label}.top_n: {old}→{cur_top-1} ({wr}%胜率，收紧)")
                continue  # 每天只动一个参数
            # top_n已到底，改score
            cur_score = get_config_value(config, cfg_map["score_path"])
            if cur_score is not None and isinstance(cur_score, (int, float)) and cur_score <= 20:
                changed, old = set_config_value(config, cfg_map["score_path"], cur_score + 3)
                if changed:
                    changes.append(f"{label}.score: {old}→{cur_score+3} (收紧评分门槛)")

        # ── 胜率>70% → 放宽（每日一次，top_n不可超过8）
        elif wr > 70:
            if _already_adjusted_today(label):
                print(f"    已调过 {label}，跳过（每日限1次）")
                continue
            cur_top = get_config_value(config, cfg_map["top_n_path"])
            if cur_top is not None and cur_top < 8:
                changed, old = set_config_value(config, cfg_map["top_n_path"], cur_top + 1)
                if changed:
                    changes.append(f"{label}.top_n: {old}→{cur_top+1} ({wr}%胜率，放宽)")

        # ── 亏损严重 → 收紧止损 ──
        if avg_pnl < -3:
            stop_path = ["stop_loss", dim, "hard_stop_pct"]
            cur_stop = get_config_value(config, stop_path)
            if cur_stop is not None:
                new_stop = round(cur_stop + 1, 1)  # -5→-4 (收窄)
                if new_stop < 0:
                    changed, old = set_config_value(config, stop_path, new_stop)
                    if changed:
                        changes.append(f"{label}.hard_stop: {old}→{new_stop}% (亏损{avg_pnl}% 收窄止损)")

    return changes


def update_feedback_json(trade_analysis, catalyst_analysis, error_analysis, changes, state, config):
    """更新 feedback.json + 写回修改后的 config"""
    today = datetime.date.today().isoformat()

    # 保留已有L1记录
    existing_records = []
    fb_path = ROOT / "trading" / "feedback.json"
    if fb_path.exists():
        try:
            existing = json.loads(fb_path.read_text())
            existing_records = existing.get('L1_emotion', {}).get('records', [])
        except:
            pass

    adj_history = []
    for ch in changes:
        parts = ch.split(":", 1)
        adj_history.append({"target": parts[0], "action": parts[1] if len(parts) > 1 else ch, "applied": True})

    fb = {
        "meta": {"description": "全系统反馈数据 — 自动进化调参",
                 "version": "2.0", "created": "2026-05-24", "last_updated": today},
        "L1_emotion": {
            "records": existing_records,
            "stats": {"total_predictions": len(existing_records), "last_updated": today},
            "parameter_adjustments": []
        },
        "L2_catalyst": {
            "records": [],
            "stats": {"total_scored": catalyst_analysis.get("total_catalysts", 0),
                      "verified_count": catalyst_analysis.get("total_verified", 0),
                      "correct": catalyst_analysis.get("outcomes", {}).get("兑现", 0)},
            "weight_adjustments": []
        },
        "L3_strategy": {"records": [], "stats": {"total_candidates": 0, "selected_count": 0}},
        "L4_execution": {
            "records": [],
            "stats": {"total_trades": trade_analysis.get("total", 0),
                      "veto_reasons": error_analysis.get("by_reason", {})}
        },
        "parameter_evolution": {
            "last_adjustment": today,
            "config_version": config.get("_meta", {}).get("version", "?"),
            "adjustment_history": [{"date": today, "applied": adj_history}] if adj_history else [],
            "performance_baseline": {
                "win_rate": trade_analysis.get("win_rate", 0),
                "avg_pnl_pct": trade_analysis.get("avg_pnl_pct", 0),
                "total_closed_trades": trade_analysis.get("total", 0)
            }
        }
    }

    # 写 feedback.json
    dump_json(fb, ROOT / "trading" / "feedback.json")
    # 写回 config
    dump_json(config, CONFIG_PATH)
    return fb


def main():
    print("=" * 55)
    print("  进化反馈分析器 v2 — 自动调参")
    print(f"  运行: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 55)

    # 1. 加载
    print("\n📥 数据源...")
    trade_data = load_json(ROOT / "trading" / "模拟持仓.json")
    catalyst_db = load_json(ROOT / "trading" / "催化剂数据库.json")
    error_db = load_json(ROOT / "trading" / "trade_errors.json")
    state = load_json(ROOT / "trading" / "系统状态.json")
    config = load_json(CONFIG_PATH)

    trade_log = trade_data.get("trade_log", [])
    print(f"  trade_log: {len(trade_log)}条  催化剂: {len(catalyst_db.get('catalysts', []))}条  错误: {len(error_db.get('errors', []))}条")

    # 2. 分析
    print("\n📊 交易分析...")
    trade_analysis = analyze_trades(trade_log)
    total = trade_analysis["total"]
    print(f"  平仓: {total}笔  胜率: {trade_analysis['win_rate']}%  均盈亏: {trade_analysis['avg_pnl_pct']}%")
    for dim, s in trade_analysis["by_dimension"].items():
        tag = "🔴" if s["win_rate"] < 40 else ("🟢" if s["win_rate"] > 70 else "🟡")
        print(f"  {tag} {dim}: {s['count']}笔 胜率{s['win_rate']}% 均{s['avg_pnl_pct']}%")

    catalyst_a = analyze_catalyst_db(catalyst_db)
    error_a = analyze_errors(error_db)

    # 3a. 评分权重进化（基于分项得分 vs PnL）
    print(f"\n📐 评分权重进化...")
    linked_trades = _link_trades_to_factors(trade_log)
    if linked_trades:
        print(f"  已关联 {len(linked_trades)} 笔交易到评分记录")
        weight_changes = _adjust_factor_weights(linked_trades, config)
        if weight_changes:
            for wc in weight_changes:
                print(f"  [{wc['dim']}] {wc['factor']}: {wc['weight']} ({wc['action']})")
        else:
            print(f"  无需调整（样本不足或区分度正常）")
    else:
        print(f"  无评分记录关联（score_history.json 为空或无匹配）")
    
    # 3b. 外围参数调优
    print(f"\n🔧 外围参数调优...")
    changes = apply_config_adjustments(trade_analysis, trade_log, config)
    if changes:
        print(f"  ✅ {len(changes)}条修改:")
        for c in changes:
            print(f"    {c}")
        # 更新 config 版本
        ver_parts = config["_meta"]["version"].split(".")
        config["_meta"]["version"] = f"{ver_parts[0]}.{int(ver_parts[1]) + 1}"
        config["_meta"]["last_updated"] = datetime.date.today().isoformat()
    else:
        print("  无需修改")

    # 4. 更新文件
    print(f"\n💾 写入文件...")
    fb = update_feedback_json(trade_analysis, catalyst_a, error_a, changes, state, config)
    print(f"  feedback.json ✅  config.json ✅")
    print(f"  基线: 胜率{fb['parameter_evolution']['performance_baseline']['win_rate']}% "
          f"均盈亏{fb['parameter_evolution']['performance_baseline']['avg_pnl_pct']}% "
          f"共{fb['parameter_evolution']['performance_baseline']['total_closed_trades']}笔")

    # 5. 记录到 memory
    if changes:
        mem_path = ROOT / "memory" / f"{datetime.date.today().isoformat()}.md"
        try:
            with open(mem_path, 'a') as f:
                f.write(f"\n## 自动进化调参 ({datetime.datetime.now().strftime('%H:%M')})\n")
                for c in changes:
                    f.write(f"- {c}\n")
                f.write(f"- config版本→{config['_meta']['version']}\n\n")
            print(f"  memory日志 ✅")
        except Exception as e:
            print(f"  memory写入失败: {e}")

    print(f"\n{'='*55}")
    print(f"  完成. config v{config['_meta']['version']}")
    print(f"{'='*55}")
    return changes


if __name__ == '__main__':
    main()
