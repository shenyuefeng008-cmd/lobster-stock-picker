#!/usr/bin/env python3
"""
产业逻辑框架 — 赛道状态更新脚本 v1.0
用法: python3 update_sector_status.py "液冷" "🟡产能爬坡期"
"""
import sys
import re
from pathlib import Path

FILE = Path(__file__).parent.parent / 'trading' / '产业逻辑框架.md'

def update(sector: str, new_status: str) -> bool:
    if not FILE.exists():
        print(f"❌ 文件不存在: {FILE}")
        return False
    
    content = FILE.read_text(encoding='utf-8')
    
    # 正则：精确匹配第一列=赛道名的行
    # group(1) = "| 液冷 |"
    # group(2) = " 描述... "
    # group(3) = "| 🔴 超级短缺 |"
    # group(4) = " ★★★★★ | #1 |"
    pat = re.compile(
        r'^(\|\s*' + re.escape(sector) + r'\s*\|)(.+?)(\|\s*[🔴🟡🟢][^\|]+\s*\|)(.+)$',
        re.UNICODE | re.MULTILINE
    )
    
    new_content, n = pat.subn(
        lambda m: m.group(1) + m.group(2) + f'| {new_status} |' + m.group(4),
        content
    )
    
    if n == 0:
        print(f"❌ 未找到赛道: {sector}")
        for i, line in enumerate(content.splitlines()):
            if sector in line and line.strip().startswith('|'):
                print(f"   近似第{i+1}行: {line.strip()[:80]}")
        return False
    elif n > 1:
        print(f"⚠️  找到{n}个匹配，仅更新第一个")
    
    FILE.write_text(new_content, encoding='utf-8')
    print(f"✅ 已更新: {sector} → {new_status}")
    return True

if __name__ == '__main__':
    if len(sys.argv) != 3:
        print("用法: python3 update_sector_status.py <赛道名> <新状态>")
        print("示例: python3 update_sector_status.py '液冷' '🟡产能爬坡期'")
        sys.exit(1)
    
    if update(sys.argv[1], sys.argv[2]):
        sys.exit(0)
    else:
        sys.exit(1)
