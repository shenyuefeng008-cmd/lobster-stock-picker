#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Bug日志模块 - 提供 log_bug() 函数，供 simulated_trading.py 等脚本调用
自动写入 trading/BUG_LOG.md，编号自动递增
"""

import sys
from pathlib import Path
import re
import datetime

# 日志文件路径
BUG_LOG = Path(__file__).resolve().parent.parent / "trading" / "BUG_LOG.md"


def _get_next_id():
    """自动获取下一个 BUG/ERROR 编号"""
    if not BUG_LOG.exists():
        return "BUG-001"
    max_num = 0
    content = BUG_LOG.read_text(encoding="utf-8")
    for line in content.splitlines():
        m = re.search(r"## (BUG|ERROR)-(\d+)", line)
        if m:
            num = int(m.group(2))
            if num > max_num:
                max_num = num
    return "BUG-%03d" % (max_num + 1)


def log_bug(title, root_cause, fix, prevention, bug_id=None, date=None, level="BUG"):
    """
    记录错误到 BUG_LOG.md
    
    参数:
        title:      一句话描述（必须）
        root_cause: 根因（必须）
        fix:        修复方案（必须）
        prevention: 预防措施（必须）
        bug_id:     编号（None=自动生成）
        date:       发现日期 YYYY-MM-DD（None=今天）
        level:      BUG 或 ERROR（默认BUG）
    
    返回: 实际写入的 bug_id
    """
    if bug_id is None:
        bug_id = _get_next_id()
    if date is None:
        date = datetime.date.today().strftime("%Y-%m-%d")
    
    entry = "\n## %s：%s\n" % (bug_id, title)
    entry += "- **日期**：%s\n" % date
    entry += "- **根因**：%s\n" % root_cause
    entry += "- **修复**：%s\n" % fix
    entry += "- **预防**：%s\n" % prevention
    entry += "\n---\n"
    
    try:
        with open(BUG_LOG, "a", encoding="utf-8") as f:
            f.write(entry)
        print("记录 %s 到 BUG_LOG.md" % bug_id, file=sys.stderr)
        return bug_id
    except Exception as e:
        print("写入 BUG_LOG 失败: %s" % str(e), file=sys.stderr)
        return None


def check_market_value_consistency(data):
    """
    检查 market_value 一致性（防止 BUG-010 再次发生）
    data = _load() 的返回值
    如果不一致，自动记录 BUG
    """
    positions = data.get("positions", [])
    calculated_mv = sum(p.get("cost", 0) for p in positions)
    stored_mv = data.get("capital", {}).get("market_value", 0)
    
    # 允许 1% 误差（成本价 vs 实时价）
    if stored_mv > 0 and abs(calculated_mv - stored_mv) > stored_mv * 0.01:
        log_bug(
            title="market_value 不一致（回归 BUG-010）",
            root_cause="sell()/buy() 后未调用 _update_capital_after_trade()",
            fix="立即调用 _update_capital_after_trade() 重新计算",
            prevention="所有 trade 操作后必须调用 _update_capital_after_trade()",
            level="BUG"
        )
        return False
    return True


def check_total_assets_consistency(data):
    """
    检查 total_assets 一致性（防止 BUG-012 再次发生）
    total_assets = available + market_value
    """
    capital = data.get("capital", {})
    # 兼容 available 和 available_cash 两种字段名
    available = capital.get("available", capital.get("available_cash", 0))
    mv = capital.get("market_value", 0)
    total = capital.get("total_assets", 0)
    
    expected_total = available + mv
    if abs(total - expected_total) > 100:  # 允许1分钱误差
        log_bug(
            title="total_assets 不一致（回归 BUG-012）",
            root_cause="available_cash 或 market_value 更新不同步",
            fix="重新计算 total_assets = available_cash + market_value",
            prevention="buy()/sell() 后同时更新 available_cash 和 market_value",
            level="BUG"
        )
        return False
    return True


if __name__ == "__main__":
    # 测试
    print("测试 log_bug()...")
    new_id = log_bug(
        title="测试错误",
        root_cause="测试根因",
        fix="测试修复",
        prevention="测试预防",
        level="BUG"
    )
    print("写入 ID: %s" % new_id)
