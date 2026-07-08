#!/usr/bin/env python3
"""
Append news items to the specified section in a news markdown file.
"""

import sys
import os

def append_news_to_section(file_path, section_name, news_items):
    """
    Append news items to a specific section in the news file.
    
    Args:
        file_path: Path to the news markdown file
        section_name: Section name (e.g., 【收盘要闻】)
        news_items: List of tuples (publish_date, title, source, sector, impact, verified)
    """
    if not os.path.exists(file_path):
        print(f"File not found: {file_path}")
        return False
    
    with open(file_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    # Find the section and the table end
    section_found = False
    table_end_idx = None
    header_line_count = 0
    
    for i, line in enumerate(lines):
        if section_name in line:
            section_found = True
            # Find the table header and separator
            for j in range(i+1, len(lines)):
                if lines[j].startswith('|') and '---' in lines[j]:
                    header_line_count = 2  # header + separator
                    table_end_idx = j + 1
                    break
                elif lines[j].startswith('|') and '发布日期' in lines[j]:
                    header_line_count = 1
                elif lines[j].strip() == '' or lines[j].startswith('---'):
                    # End of section reached without finding table end
                    table_end_idx = j
                    break
            break
    
    if not section_found:
        print(f"Section {section_name} not found in {file_path}")
        return False
    
    if table_end_idx is None:
        print(f"Table end not found in section {section_name}")
        return False
    
    # Build the new lines to insert
    new_lines = []
    for item in news_items:
        publish_date, title, source, sector, impact, verified = item
        new_line = f"| {publish_date} | {title} | {source} | {sector} | {impact} | {verified} |\n"
        new_lines.append(new_line)
    
    # Insert the new lines at table_end_idx
    updated_lines = lines[:table_end_idx] + new_lines + lines[table_end_idx:]
    
    # Write back
    with open(file_path, 'w', encoding='utf-8') as f:
        f.writelines(updated_lines)
    
    print(f"Successfully appended {len(news_items)} news items to {section_name}")
    return True


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python3 append_news.py <news_file>")
        sys.exit(1)
    
    news_file = sys.argv[1]
    
    # Hardcoded news items for testing
    # In production, these would be passed as arguments or read from stdin
    news_items = [
        ("2026-06-21", "伊朗武装部队宣布霍尔木兹海峡关闭", "新华社/伊朗法尔斯通讯社", "能源/航运/地缘政治", "🔴高", "已核实"),
        ("2026-06-21", "国务院新闻办6月22日下午3时发布会介绍利用外资政策", "国新办", "政策/A股", "🟡中", "已核实"),
        ("2026-06-21", "上交所拟完善股票期权组合策略业务推出单边平仓功能", "陆家嘴财经早餐", "金融/衍生品", "🟡中", "待核实"),
        ("2026-06-21", "下周(6月22日-28日)市场大事预告：LPR、MLF到期、解禁549亿", "Wind", "宏观/A股", "🟡中", "已核实"),
    ]
    
    append_news_to_section(news_file, "【收盘要闻】", news_items)
