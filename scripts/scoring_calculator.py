#!/usr/bin/env python3
"""
龙虾量化打分计算器 v2.1
用法：python3 scoring_calculator.py --dimension 1.0_一进二 --data-file trading/stock_data.json
输出：按分数从高到低排序的候选股列表
"""

import json
import argparse
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent

# 打分模型定义
SCORING_MODELS = {
    "1.0_一进二": {
        "指标": [
            {"name": "竞量比", "weight": 0.3, "ranges": [
                {"min": 20, "score": 30},
                {"min": 15, "max": 20, "score": 20},
                {"min": 10, "max": 15, "score": 10},
                {"max": 10, "score": 0}
            ]},
            {"name": "高开幅度", "weight": 0.2, "ranges": [
                {"min": 6, "max": 10, "score": 20},
                {"min": 4, "max": 6, "score": 10},
                {"min": 10, "max": 15, "score": 10},
                {"score": 0}
            ]},
            {"name": "首板成交额(万)", "weight": 0.2, "ranges": [
                {"max": 5000, "score": 20},
                {"min": 5000, "max": 8000, "score": 10},
                {"min": 8000, "score": 0}
            ]},
            {"name": "板块强度(涨停家数)", "weight": 0.15, "ranges": [
                {"min": 5, "score": 15},
                {"min": 3, "max": 5, "score": 10},
                {"max": 3, "score": 0}
            ]},
            {"name": "换手实体板", "weight": 0.15, "ranges": [
                {"value": True, "score": 15},
                {"value": False, "score": 0}
            ]}
        ],
        "入选阈值": 60
    },
    "1.0_分歧低吸": {
        "指标": [
            {"name": "连板高度", "weight": 0.3, "ranges": [
                {"min": 3, "score": 30},
                {"min": 2, "max": 3, "score": 20},
                {"min": 1, "max": 2, "score": 10},
                {"max": 1, "score": 0}
            ]},
            {"name": "低开幅度", "weight": 0.2, "ranges": [
                {"min": -3, "max": -1, "score": 20},
                {"min": -5, "max": -3, "score": 10},
                {"min": -1, "max": 0, "score": 10},
                {"max": -5, "score": 0},
                {"min": 0, "score": 0}
            ]},
            {"name": "成交额衰减", "weight": 0.2, "ranges": [
                {"max": 0.3, "score": 20},
                {"min": 0.3, "max": 0.5, "score": 10},
                {"min": 0.5, "score": 0}
            ]},
            {"name": "板块延续(涨停家数)", "weight": 0.15, "ranges": [
                {"min": 3, "score": 15},
                {"min": 1, "max": 3, "score": 10},
                {"max": 1, "score": 0}
            ]},
            {"name": "均线支撑", "weight": 0.15, "ranges": [
                {"value": "MA5上方", "score": 15},
                {"value": "MA5-MA10之间", "score": 10},
                {"value": "跌破MA10", "score": 0}
            ]}
        ],
        "入选阈值": 60
    },
    "2.0_板块卡位": {
        "指标": [
            {"name": "板块涨停家数", "weight": 0.4, "ranges": [
                {"min": 5, "score": 40},
                {"min": 3, "max": 5, "score": 30},
                {"max": 3, "score": 0, "硬约束": True}
            ]},
            {"name": "前排股成交额(亿)", "weight": 0.3, "ranges": [
                {"min": 5, "score": 30},
                {"min": 3, "max": 5, "score": 20},
                {"min": 1, "max": 3, "score": 10},
                {"max": 1, "score": 0}
            ]},
            {"name": "板块地位", "weight": 0.2, "ranges": [
                {"value": "龙头", "score": 20},
                {"value": "前排", "score": 15},
                {"value": "中后排", "score": 5}
            ]},
            {"name": "分时强度(高开%)", "weight": 0.1, "ranges": [
                {"min": 5, "score": 10},
                {"min": 0, "max": 5, "score": 5},
                {"max": 0, "score": 0}
            ]}
        ],
        "入选阈值": 70
    },
    "3.0_趋势低吸": {
        "指标": [
            {"name": "产业逻辑强度", "weight": 0.3, "ranges": [
                {"value": "L1", "score": 30},
                {"value": "L2", "score": 20},
                {"value": "L3", "score": 10},
                {"value": "L4", "score": 0}
            ]},
            {"name": "均线排列", "weight": 0.2, "ranges": [
                {"value": "MA5>MA10>MA20", "score": 20},
                {"value": "MA5>MA10但MA10<MA20", "score": 10},
                {"value": "其他", "score": 0}
            ]},
            {"name": "回踩位置", "weight": 0.2, "ranges": [
                {"value": "MA5", "score": 20},
                {"value": "MA10", "score": 15},
                {"value": "跌破MA10", "score": 0}
            ]},
            {"name": "成交额(亿)", "weight": 0.15, "ranges": [
                {"min": 10, "score": 15},
                {"min": 5, "max": 10, "score": 10},
                {"min": 3, "max": 5, "score": 5},
                {"max": 3, "score": 0, "硬约束": True}
            ]},
            {"name": "涨跌家数环境", "weight": 0.15, "ranges": [
                {"value": "连续2日>1500", "score": 15},
                {"value": "单日>1500", "score": 10},
                {"value": "<1500", "score": 0, "硬约束": True}
            ]}
        ],
        "入选阈值": 70
    }
}


# 尝试从 lobster-config.json 加载打分模型（覆盖上方硬编码）
try:
    _config_path = os.path.join(os.path.dirname(__file__), "..", "lobster-config.json")
    with open(_config_path, "r", encoding="utf-8") as _f:
        _config = _json.load(_f)
    if "scoring_models" in _config:
        SCORING_MODELS = _config["scoring_models"]
except Exception:
    pass  # 使用上方硬编码的兜底值

def calculate_score(stock_data, dimension):
    """计算单只股票得分"""
    model = SCORING_MODELS.get(dimension)
    if not model:
        raise ValueError(f"未知的维度: {dimension}")
    
    total_score = 0
    details = []
    
    for indicator in model["指标"]:
        name = indicator["name"]
        weight = indicator["weight"]
        value = stock_data.get(name)
        
        if value is None:
            details.append(f"{name}: N/A (0分)")
            continue
        
        # 查找匹配的分数段
        score = 0
        for r in indicator["ranges"]:
            if "硬约束" in r and r["硬约束"] and value < (r.get("min") or 0):
                return 0, [f"{name}: 硬约束不满足 (0分，淘汰)"]
            
            if "min" in r and "max" in r:
                if r["min"] <= value < r["max"]:
                    score = r["score"]
                    break
            elif "min" in r:
                if value >= r["min"]:
                    score = r["score"]
                    break
            elif "max" in r:
                if value < r["max"]:
                    score = r["score"]
                    break
            elif "value" in r:
                if value == r["value"]:
                    score = r["score"]
                    break
        
        weighted_score = score * weight
        total_score += weighted_score
        details.append(f"{name}: {value} → {score}分 (权重{weight*100}%，加权{weighted_score:.1f}分)")
    
    return total_score, details

def main():
    parser = argparse.ArgumentParser(description="龙虾量化打分计算器")
    parser.add_argument("--dimension", required=True, choices=SCORING_MODELS.keys(), help="打分维度")
    parser.add_argument("--data-file", required=True, help="JSON数据文件路径，包含股票数据数组")
    args = parser.parse_args()
    
    # 读取数据
    with open(args.data_file, "r", encoding="utf-8") as f:
        stocks = json.load(f)
    
    # 计算得分
    results = []
    for stock in stocks:
        score, details = calculate_score(stock, args.dimension)
        if score >= SCORING_MODELS[args.dimension]["入选阈值"]:
            results.append({"stock": stock, "score": score, "details": details})
    
    # 按分数排序
    results.sort(key=lambda x: x["score"], reverse=True)
    
    # 输出结果
    print(f"\n✅ {args.dimension} 打分结果（按分数排序）\n")
    for i, r in enumerate(results, 1):
        stock = r["stock"]
        print(f"【第{i}名】{stock.get('名称', '未知')}({stock.get('代码', '未知')}) — 总分：{r['score']:.1f}")
        print(f"  买入条件：{stock.get('买入条件', '待定')}")
        print(f"  仓位：{stock.get('仓位', '0%')}")
        print(f"  打分明细：")
        for detail in r["details"]:
            print(f"    - {detail}")
        print()
    
    # 输出前3名（或前2名，根据维度）
    limit = 3 if "一进二" in args.dimension else 2
    if "板块卡位" in args.dimension:
        limit = 1
    
    print(f"\n📊 入选名单（前{limit}名）：")
    for i, r in enumerate(results[:limit], 1):
        stock = r["stock"]
        print(f"{i}. {stock.get('名称', '未知')}({stock.get('代码', '未知')}) — {r['score']:.1f}分")
    
    # 保存结果到JSON
    output_file = str(ROOT / "trading" / f"scoring_result_{args.dimension}.json")
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"\n💾 完整结果已保存：{output_file}\n")
    
    # 额外保存分项得分JSON（权重进化用）
    factor_file = str(ROOT / "trading" / f"scoring_factor_{args.dimension}.json")
    factor_data = []
    for r in results:
        stock_code = r["stock"].get("代码", "?")
        stock_name = r["stock"].get("名称", "?")
        score, factors = calculate_score_structured(r["stock"], args.dimension)
        factor_data.append({"code": stock_code, "name": stock_name, "total_score": round(score, 1), "factors": factors})
    with open(factor_file, "w", encoding="utf-8") as f:
        json.dump({"dimension": args.dimension, "date": "", "candidates": factor_data}, f, ensure_ascii=False, indent=2)
    print(f"💾 分项得分已保存：{factor_file}")

if __name__ == "__main__":
    main()
