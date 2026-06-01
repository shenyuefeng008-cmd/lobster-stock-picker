#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
催化剂评分模块 - 可进化版本
从 lobster-config.json 读取权重，输出五维评分和催化剂等级
"""

import json
import sys
from pathlib import Path

# 配置文件路径
CONFIG_FILE = Path(__file__).parent.parent / "lobster-config.json"
CATALYST_DB = Path(__file__).parent.parent / "trading" / "催化剂数据库.json"


def load_config():
    """加载配置文件"""
    with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)


def load_catalyst_database():
    """加载催化剂数据库 (兼容函数名)"""
    return load_catalyst_db()

def load_catalyst_db():
    """加载催化剂数据库"""
    if not CATALYST_DB.exists():
        return {"catalysts": [], "metadata": {}}
    with open(CATALYST_DB, 'r', encoding='utf-8') as f:
        return json.load(f)


def get_payoff_score(period):
    """将兑现周期转换为分数"""
    mapping = {
        'T0': 25,  # 当日事件交易
        'T1': 20,  # 1-2周
        'T2': 15,  # 1-2季度
        'T3': 5,   # 1-3年
    }
    return mapping.get(period, 10)


def get_tradability_score(sector_name, stock_code):
    """
    计算可交易性评分（简化版）
    实际应该从盘口数据获取：成交额、主动买卖、龙头带动性
    """
    # TODO: 接入实时盘口数据
    # 当前返回默认值
    return 3  # 0-5分


def calculate_catalyst_score(sector_name, catalyst_data=None):
    """
    计算催化剂五维评分
    
    Args:
        sector_name: 板块名称
        catalyst_data: 催化剂数据字典（可选，若不提供则从数据库读取）
    
    Returns:
        dict: {
            'score': 总分(0-100),
            'grade': 等级(S/A/B/C/D),
            'details': 五维分项分数字典
        }
    """
    config = load_config()
    weights = config['catalyst']['scoring_weights']
    thresholds = config['catalyst']['grade_thresholds']
    heat_penalty = config['catalyst']['heat_penalty']
    
    # 如果没有提供catalyst_data，从数据库读取
    if catalyst_data is None:
        db = load_catalyst_db()
        catalyst_data = None
        for c in db['catalysts']:
            if c['sector'] == sector_name:
                catalyst_data = c
                break
        
        # 如果数据库中没有，使用默认值
        if catalyst_data is None:
            catalyst_data = {
                'fact_strength': 3,
                'expectation_diff': 3,
                'heat': 3,
                'payoff_period': 'T2',
                'tradability': 3
            }
    
    # 五维评分（每项0-5分，乘以权重后转换为0-100分）
    fact_strength_score = catalyst_data['fact_strength'] / 5 * 100
    expectation_diff_score = catalyst_data['expectation_diff'] / 5 * 100
    heat_score = (5 - catalyst_data['heat']) / 5 * 100  # 热度越低分越高
    payoff_score = get_payoff_score(catalyst_data['payoff_period']) / 25 * 100
    tradability_score = catalyst_data['tradability'] / 5 * 100
    
    # 加权总分
    total_score = (
        fact_strength_score * weights['fact_strength'] +
        expectation_diff_score * weights['expectation_diff'] +
        heat_score * weights['heat'] +
        payoff_score * weights['payoff_period'] +
        tradability_score * weights['tradability']
    )
    
    # 热度降权
    if heat_penalty['enabled'] and catalyst_data['heat'] >= heat_penalty['threshold']:
        total_score *= (1 - heat_penalty['penalty_pct'])
    
    # 限制在0-100范围内
    total_score = max(0, min(100, total_score))
    
    # 判断等级
    if total_score >= thresholds['S']:
        grade = 'S'
    elif total_score >= thresholds['A']:
        grade = 'A'
    elif total_score >= thresholds['B']:
        grade = 'B'
    elif total_score >= thresholds['C']:
        grade = 'C'
    else:
        grade = 'D'
    
    return {
        'score': round(total_score, 2),
        'grade': grade,
        'details': {
            'fact_strength': round(fact_strength_score, 2),
            'expectation_diff': round(expectation_diff_score, 2),
            'heat': round(heat_score, 2),
            'payoff_period': round(payoff_score, 2),
            'tradability': round(tradability_score, 2)
        }
    }


def get_catalyst_action(grade):
    """
    根据催化剂等级返回对应动作
    
    Returns:
        str: 'strong_buy' / 'buy' / 'observe' / 'watch_only' / 'block'
    """
    config = load_config()
    return config['catalyst']['grade_action'].get(grade, 'watch_only')


def update_catalyst_verification(sector_name, outcome):
    """
    更新催化剂验证结果（收盘后调用）
    
    Args:
        sector_name: 板块名称
        outcome: '兑现' / '部分兑现' / '未兑现' / '证伪'
    """
    db = load_catalyst_db()
    
    for catalyst in db['catalysts']:
        if catalyst['sector'] == sector_name and not catalyst['verified']:
            catalyst['verified'] = True
            catalyst['outcome'] = outcome
            catalyst['evolution_note'] = f"验证结果: {outcome}"
            
            # 更新metadata
            db['metadata']['verified_count'] += 1
            db['metadata']['last_verification'] = sector_name
            break
    
    with open(CATALYST_DB, 'w', encoding='utf-8') as f:
        json.dump(db, f, ensure_ascii=False, indent=2)


def main():
    """命令行测试接口"""
    if len(sys.argv) < 2:
        print("用法: python3 catalyst_scoring.py <板块名称>")
        sys.exit(1)
    
    sector = sys.argv[1]
    result = calculate_catalyst_score(sector)
    
    print(f"板块: {sector}")
    print(f"催化剂总分: {result['score']}")
    print(f"催化剂等级: {result['grade']}")
    print(f"建议动作: {get_catalyst_action(result['grade'])}")
    print(f"\n五维分项:")
    for key, value in result['details'].items():
        print(f"  {key}: {value}")


if __name__ == '__main__':
    main()
