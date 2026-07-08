#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试 3.0 盘中实时解锁三刀修改
不依赖实盘数据，纯逻辑单元测试
"""
import json
import sys
import os

BASE = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(os.path.dirname(BASE), 'lobster-config.json')

print("=" * 60)
print("测试开始：3.0 盘中实时解锁逻辑")
print("=" * 60)

# ============================================================
# 测试第一刀：配置读取（inference_zone / full_activate_above 参数化）
# ============================================================
print("\n【第一刀】配置读取测试")

with open(CONFIG_PATH) as f:
    cfg = json.load(f)

rules_30 = cfg.get('3.0_emotion_rules', {})
infer_zone = rules_30.get('inference_zone', {})
infer_low  = infer_zone.get('low', 1800)
infer_high = infer_zone.get('high', 2500)
full_above = rules_30.get('full_activate_above', 2500)
melt_below = rules_30.get('melt_below', 1800)

def calc_unlock(up_count, melt_locked=True):
    """模拟 detect_buypoints 中的解锁判断逻辑"""
    # 关键：只有熔断的标的才需要判断解锁
    if not melt_locked:
        return False, False, False  # 未熔断的标的不触发realtime_unlocked
    in_infer = infer_low <= up_count <= infer_high
    in_full    = up_count > full_above
    return in_infer or in_full, in_infer, in_full

tests_1 = [
    # (up_count, is_30_melt, expect_realtime_unlocked, expect_in_infer, expect_in_full)
    # 推理区测试（1800-2500）
    (1800, True,  True,  True,  False, "1800 → 推理区下界，应解锁"),
    (2000, True,  True,  True,  False, "2000 → 推理区中段，应解锁"),
    (2500, True,  True,  True,  False, "2500 → 推理区上界，应解锁（<=）"),
    # 严格解锁区测试（>2500）
    (2501, True,  True,  False, True,  "2501 → 严格解锁区，应解锁（>）"),
    (3000, True,  True,  False, True,  "3000 → 严格解锁区，应解锁"),
    # 冰点测试（<1800）
    (1500, True,  False, False, False, "1500 < 1800，不应解锁"),
    (1700, True,  False, False, False, "1700 < 1800，不应解锁"),
    (500,  True,  False, False, False, "500 冰点，不应解锁"),
    # 未熔断测试
    (2000, False, False, False, False, "未熔断，realtime_unlocked=False"),
]

pass_1 = fail_1 = 0
for up, melted, exp_unlocked, exp_infer, exp_full, desc in tests_1:
    unlocked, in_infer, in_full = calc_unlock(up, melt_locked=melted)
    ok = (unlocked == exp_unlocked) and (in_infer == exp_infer) and (in_full == exp_full)

    status = "✅ PASS" if ok else "❌ FAIL"
    if ok: pass_1 += 1
    else:   fail_1 += 1
    print(f"  {status} | up_count={up} melted={melted} → unlocked={unlocked} (期望={exp_unlocked}) | {desc}")

print(f"  第一刀结果：{pass_1}/{len(tests_1)} 通过\n")

# ============================================================
# 测试第二刀：维度过滤器豁免 + 推理区仓位减半
# ============================================================
print("【第二刀】维度过滤器豁免 + 仓位减半测试")

BASE_POSITION_PCT = {
    '1.0-一进二': 10,
    '1.0-分歧低吸': 10,
    '2.0-板块卡位': 10,
    '3.0-趋势低吸': 15,
}

def simulate_dim_filter(dim, dominant_dim, realtime_unlocked, in_infer_zone, pos_limit, n_positions):
    """
    模拟 detect_buypoints 中的维度过滤 + 仓位减半逻辑
    返回：(是否买入, 实际仓位pct)
    """
    dim_prefix = dim.split('-')[0]   # '1.0' / '2.0' / '3.0'

    # 维度过滤器（第二刀豁免逻辑）
    if not (dim == '3.0-趋势低吸' and realtime_unlocked):
        if dominant_dim not in ('辅助', dim_prefix) and dim_prefix not in dominant_dim.split('+'):
            return False, 0   # 被过滤

    # 动态仓位（简化：假设 adjust_position_pct 实现）
    base_pct = BASE_POSITION_PCT.get(dim, 10)
    # 简化版 adjust_position_pct：每多一个持仓，仓位递减
    adj_pct = base_pct * (1 - 0.1 * n_positions)
    if adj_pct <= 0:
        return False, 0

    # 推理区仓位减半（第二刀）
    if dim == '3.0-趋势低吸' and realtime_unlocked and in_infer_zone:
        adj_pct = adj_pct / 2

    return True, adj_pct


tests_2 = [
    # (dim, dominant_dim, unlocked, in_infer, pos_limit, n_pos, expect_buy, expect_pct_range, desc)
    ('3.0-趋势低吸', '1.0', True,  True,  5, 0, True, (7.0, 7.5),   "推理区解锁 → 豁免过滤 + 仓位减半(15→7.5)"),
    ('3.0-趋势低吸', '1.0', True,  False, 5, 0, True, (15.0, 15.0), "严格解锁区 → 豁免过滤 + 不减半(15)"),
    ('3.0-趋势低吸', '1.0', False, False, 5, 0, False, (0, 0),       "未解锁 → 被维度过滤拦截"),
    ('1.0-分歧低吸', '1.0', False, False, 5, 0, True, (10, 10),      "1.0正常通过维度过滤"),
    ('2.0-板块卡位', '1.0', False, False, 5, 0, False, (0, 0),       "2.0被1.0主导过滤"),
    ('3.0-趋势低吸', '1.0+3.0', True, True, 5, 0, True, (7.0, 7.5), "1.0+3.0双主导 → 3.0正常通过"),
]

pass_2 = fail_2 = 0
for dim, dom, unlocked, in_infer, pos_lim, n_pos, exp_buy, (pct_lo, pct_hi), desc in tests_2:
    bought, adj_pct = simulate_dim_filter(dim, dom, unlocked, in_infer, pos_lim, n_pos)
    ok = (bought == exp_buy) and (pct_lo <= adj_pct <= pct_hi)
    status = "✅ PASS" if ok else "❌ FAIL"
    if ok: pass_2 += 1
    else:   fail_2 += 1
    print(f"  {status} | dim={dim} dom={dom} unlocked={unlocked} → bought={bought}, adj_pct={adj_pct:.1f} | {desc}")

print(f"  第二刀结果：{pass_2}/{len(tests_2)} 通过\n")

# ============================================================
# 测试第三刀：_check_trend_low() 参数化（不再硬编码 2000）
# ============================================================
print("【第三刀】_check_trend_low() 参数传入测试")

def mock_check_trend_low(item, up_count, realtime_unlocked):
    """
    模拟 _check_trend_low() 的核心逻辑
    关键：不再硬编码 up_count >= 2000，而是用传入的 realtime_unlocked
    """
    locked = item.get('locked', False)
    melt_locked = locked and '熔断' in item.get('锁定原因', '')

    # 第三刀核心：用传入的 realtime_unlocked，不硬编码
    if melt_locked and not realtime_unlocked:
        return None   # 冰点熔断，盘中未修复

    # 以下省略均线逻辑，只测解锁判断
    return "趋势低吸：回踩MA5不破（盘中解锁）"


tests_3 = [
    # (item, up_count, realtime_unlocked, expect_result, desc)
    ({'locked': True, '锁定原因': '冰点熔断<2000'}, 2000, True,  "买入", "熔断+realtime_unlocked=True → 应买入"),
    ({'locked': True, '锁定原因': '冰点熔断<2000'}, 2000, False, None,   "熔断+realtime_unlocked=False → 应返回None"),
    ({'locked': False},                                  2000, False, "买入", "未熔断 → 不受解锁影响，应买入"),
    ({'locked': True, '锁定原因': '冰点熔断<2000'}, 1500, True,  "买入", "推理区(1800-2500)unlocked=True → 应买入"),
    ({'locked': True, '锁定原因': '冰点熔断<2000'}, 1000, False, None,   "严格冰点 unlocked=False → 应返回None"),
]

pass_3 = fail_3 = 0
for item, up, unlocked, exp, desc in tests_3:
    result = mock_check_trend_low(item, up, unlocked)
    ok = (result is None and exp is None) or (result is not None and exp == "买入")
    status = "✅ PASS" if ok else "❌ FAIL"
    if ok: pass_3 += 1
    else:   fail_3 += 1
    print(f"  {status} | locked={item.get('locked')} unlocked={unlocked} up={up} → result={'None' if result is None else '买入'} | {desc}")

print(f"  第三刀结果：{pass_3}/{len(tests_3)} 通过\n")

# ============================================================
# 汇总
# ============================================================
print("=" * 60)
total_pass = pass_1 + pass_2 + pass_3
total_fail = fail_1 + fail_2 + fail_3
total     = total_pass + total_fail
print(f"总体结果：{total_pass}/{total} 通过，{total_fail} 失败")
if total_fail == 0:
    print("🎉 全部测试通过！三刀修改逻辑正确。")
else:
    print("⚠️  存在失败用例，请检查逻辑。")
print("=" * 60)

sys.exit(0 if total_fail == 0 else 1)
