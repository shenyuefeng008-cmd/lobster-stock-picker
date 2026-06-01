#!/usr/bin/env python3
"""
龙虾竞价选股 — 过滤脚本 v2.1
读取 /tmp/lobster_bid_input.json，过滤，输出 /tmp/lobster_bid_result.json
修复：字段名"涨跌家数"→"上涨家数"，字典缺逗号语法错误
"""

import json, re, sys
import os

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "..", "lobster-config.json")
try:
    with open(CONFIG_PATH) as _cf:
        _cfg = json.load(_cf)
    BID_THRESHOLDS = _cfg.get("bid_filter_thresholds", {})
except Exception:
    BID_THRESHOLDS = {}

print("=== 龙虾竞价选股过滤开始 ===\n")

# ============================================
# 步骤1：读取输入文件
# ============================================
print("步骤1：读取输入文件...")
try:
    with open("/tmp/lobster_bid_input.json") as f:
        data = json.load(f)
    emotion = data['emotion']
    print(f"✅ 读取成功，日期：{data['date']}")
    print(f"情绪：上涨{emotion['上涨家数']}家，主导维度：{emotion['主导维度']}\n")
except Exception as e:
    print(f"❌ 错误：无法读取输入文件：{e}")
    sys.exit(1)

# ============================================
# 步骤2：解析竞价数据（腾讯接口）
# ============================================
print("步骤2：解析竞价数据...")
bidding_data = {}
raw = data.get('bidding_raw', '')
for line in raw.split(';'):
    line = line.strip()
    if not line:
        continue
    m = re.search(r'v_(\w+)="([^"]*)"', line)
    if m:
        code = m.group(1)
        parts = m.group(2).split('~')
        if len(parts) > 36:
            try:
                bidding_data[code] = {
                    'name': parts[1],
                    'change_pct': float(parts[32]) if parts[32] else 0,
                    'volume': int(parts[36]) if parts[36] else 0
                }
            except Exception:
                pass

print(f"✅ 解析成功，共{len(bidding_data)}只股票竞价数据\n")

# ============================================
# 步骤3：逐档位过滤
# ============================================
print("步骤3：逐档位过滤...\n")
print("\n" + "=" * 40)
print("🔔 关注股更新 | 竞价过滤结果")
print("=" * 40 + "\n")

results = {}

for tier_name, candidates in data['candidates'].items():
    print(f"--- 档位：{tier_name} ---")
    print(f"候选数：{len(candidates)}")

    qualified = []
    for stock in candidates:
        code = stock['代码']
        name = stock['名称']
        code_key = ('sh' + code) if code.startswith('6') else ('sz' + code)

        if code_key not in bidding_data:
            print(f"  {name}({code})：⚠️ 无竞价数据，保留监控")
            stock['竞价结果'] = '❌无竞价数据'
            qualified.append({'name': name, 'code': code, 'change_pct': None, 'volume': None})
            continue

        bd = bidding_data[code_key]
        change_pct = bd['change_pct']
        volume = bd['volume']

        # 根据档位过滤（无竞价数据时跳过过滤，保留监控）
        if change_pct is None:
            # 无竞价数据，直接保留
            qualified.append({'name': name, 'code': code, 'change_pct': change_pct, 'volume': volume})
            print(f"  {name}({code})：⚠️ 保留监控（无竞价数据）")
        elif tier_name == '1.0一进二':
            _t = BID_THRESHOLDS.get('1.0一进二', {})
            _min = _t.get('min_change_pct', 6)
            _max = _t.get('max_change_pct')
            _v = _t.get('min_volume', 1500)
            if change_pct is not None and _min <= change_pct <= (_max if _max is not None else 9999) and volume >= _v:
                qualified.append({'name': name, 'code': code, 'change_pct': change_pct, 'volume': volume})
                print(f"  {name}({code})：✅ 符合（高开{change_pct}%，竞量{volume}手）")
        elif tier_name == '1.0分歧低吸':
            _t = BID_THRESHOLDS.get('1.0分歧低吸', {})
            _min = _t.get('min_change_pct', -3)
            _max = _t.get('max_change_pct', 0)
            if change_pct is not None and _min <= change_pct <= _max:
                qualified.append({'name': name, 'code': code, 'change_pct': change_pct, 'volume': volume})
                print(f"  {name}({code})：✅ 符合（低开{change_pct}%，竞量{volume}手）")
            print(f"  {name}({code})：✅ 符合（低开{change_pct}%，竞量{volume}手）")
        elif tier_name == '2.0板块卡位':
            _t = BID_THRESHOLDS.get('2.0板块卡位', {})
            _min = _t.get('min_change_pct', 5)
            _max = _t.get('max_change_pct')
            _v = _t.get('min_volume', 1000)
            if change_pct is not None and change_pct >= _min and (_max is None or change_pct <= _max) and volume >= _v:
                qualified.append({'name': name, 'code': code, 'change_pct': change_pct, 'volume': volume})
                print(f"  {name}({code})：✅ 符合（高开{change_pct}%，竞量{volume}手）")
        elif tier_name == '3.0趋势低吸':
            # 检查3.0锁定状态（盘前引擎标记）
            is_locked = stock.get('locked', False)
            lock_reason = stock.get('locked_reason') or stock.get('锁定原因', '')
            if is_locked:
                print(f"  {name}({code})：🔒 3.0已锁定（{lock_reason}），跳过竞价")
                continue
            _t = BID_THRESHOLDS.get('3.0趋势低吸', {})
            _min = _t.get('min_change_pct', -2)
            _max = _t.get('max_change_pct', 3)
            if change_pct is not None and _min <= change_pct <= _max:
                qualified.append({'name': name, 'code': code, 'change_pct': change_pct, 'volume': volume})
                print(f"  {name}({code})：✅ 符合（高开{change_pct}%，竞量{volume}手）")
        else:
            if change_pct is not None:
                print(f"  {name}({code})：❌ 不符合（开{change_pct}%，竞量{volume}手）")

    # 选最优1个（按竞量排序）
    # 选最优1个（按竞量排序，无竞价数据排最后）
    if qualified:
        with_data = [q for q in qualified if q['change_pct'] is not None]
        without_data = [q for q in qualified if q['change_pct'] is None]
        if with_data:
            with_data.sort(key=lambda x: x['volume'] or 0, reverse=True)
            results[tier_name] = with_data[0]
            best = with_data[0]
            print(f"✅ 最优：{best['name']}({best['code']})，竞量{best['volume']}手")
        elif without_data:
            results[tier_name] = without_data[0]
            print(f"⚠️ 仅无数据候选，保留：{without_data[0]['name']}({without_data[0]['code']})")
    else:
        results[tier_name] = None
        print(f"⚠️  无符合规则标的\n")

# ============================================
# 步骤4：更新关注股.md
# ============================================
print("步骤4：更新关注股.md...")
today = data['date']
content = f"# 🎯 关注股（{today} 竞价更新）\n\n"

for tier_name, best in results.items():
    if best:
        content += f"## {tier_name}\n"
        content += f"- {best['name']}({best['code']}) — 竞价{'高开' if best['change_pct'] > 0 else '低开'}{abs(best['change_pct'])}%，竞量{best['volume']}手\n"
        content += f"  - 买入条件：若回踩5日线不破 → 低吸\n\n"
    else:
        content += f"## {tier_name}\n"
        content += f"- ⚠️ 无符合规则标的\n\n"

content += f"---\n**更新时间**：{data.get('date', today)} 09:25\n**总仓位上限**：{emotion['总仓位上限']}成\n"

try:
    with open('/Users/yuefengshen/.qclaw/workspace-1gwpiwf3hr163jz5/trading/关注股.md', 'w') as f:
        f.write(content)
    print("✅ 关注股.md 已更新")
except Exception as e:
    print(f"❌ 关注股.md 写入失败：{e}")

# ============================================
# 步骤5：保存关注股JSON（供买点检测器消费）
# v2.2：保留全部候选，仅标注竞价结果，不删除任何标的
# ============================================
try:
    watch_candidates = {
        'date': data['date'],
        'source': 'bid_filter',
        'emotion': emotion,
        'candidates': {}
    }
    
    # 构建竞价结果map（code -> result_info）
    bid_pass_map = {}
    for tier_name, best in results.items():
        if best and best.get('change_pct') is not None:
            bid_pass_map[best['code']] = {
                'bid_passed': True,
                '竞价涨幅': best['change_pct'],
                '竞价量': best['volume']
            }
    
    
    # 保留全部候选，仅标注竞价是否通过
    for tier_name in ['1.0一进二', '1.0分歧低吸', '2.0板块卡位', '3.0趋势低吸']:
        original_items = data['candidates'].get(tier_name, [])
        enriched = []
        for item in original_items:
            code = str(item.get('代码', ''))
            if code in bid_pass_map:
                # 竞价通过 → 标注
                item['竞价结果'] = '✅通过'
                item['竞价涨幅'] = bid_pass_map[code]['竞价涨幅']
                item['竞价量'] = bid_pass_map[code]['竞价量']
            else:
                # 竞价未通过 → 也保留，标注未通过
                item['竞价结果'] = '❌未通过'
            enriched.append(item)
        watch_candidates['candidates'][tier_name] = enriched
    
    with open('/tmp/lobster_watchlist_candidates.json', 'w') as f:
        json.dump(watch_candidates, f, ensure_ascii=False, indent=2)
    print("✅ 关注股JSON已保存到 /tmp/lobster_watchlist_candidates.json")
    
    # 输出关注股汇总
    print("\n" + "─" * 30)
    print("📊 今日关注股汇总")
    print("─" * 30)
    pass_count = 0
    total_count = 0
    for dim, items in watch_candidates['candidates'].items():
        dim_pass = 0
        for s in items:
            total_count += 1
            passed = s.get('竞价结果', '') == '✅通过'
            if passed:
                dim_pass += 1
                pass_count += 1
                print(f"  {dim}: {s.get('名称','?')}({s.get('代码','?')}) ✅竞价通过")
            else:
                print(f"  {dim}: {s.get('名称','?')}({s.get('代码','?')}) ❌竞价未通过(保留监控)")
        if dim_pass == 0 and items:
            pass_str = f"  {dim}: 0/{len(items)}只通过，全部保留监控"
    print(f"\n总关注股: {total_count}只 | 竞价通过: {pass_count}只 | 仓位上限: {emotion['总仓位上限']}成")
except Exception as e:
    print(f"❌ 关注股JSON写入失败：{e}")

# ============================================
# 步骤6：保存结果JSON
# ============================================
print("\n=== 保存结果 ===")
output = {
    'date': data['date'],
    'emotion': emotion,
    'results': results
}
with open('/tmp/lobster_bid_result.json', 'w') as f:
    json.dump(output, f, ensure_ascii=False, indent=2)

print(f"✅ 结果已保存到 /tmp/lobster_bid_result.json")
print("\n=== 龙虾竞价选股过滤结束 ===")
