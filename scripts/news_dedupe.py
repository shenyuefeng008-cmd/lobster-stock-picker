#!/usr/bin/env python3
"""
新闻去重辅助脚本
读取 trading/news/YYYY-MM-DD.md 已有新闻标题，用于去重
"""
import sys
import re
from pathlib import Path

def get_existing_titles(news_file: str) -> set:
    """从新闻存档文件提取已有标题"""
    p = Path(news_file)
    if not p.exists():
        return set()
    
    content = p.read_text(encoding='utf-8')
    # 匹配表格行：| 发布日期 | 标题 | 来源 | ...
    # 或列表行：- [标题](url)
    titles = set()
    
    # 表格格式
    table_pattern = r'\|[^|]+\|([^|]+)\|'
    for match in re.finditer(table_pattern, content):
        title = match.group(1).strip()
        if title and title not in ('标题', '发布日期', '---'):
            titles.add(title)
    
    # 列表格式：- [标题](url) 或 - 标题
    list_pattern = r'-\s+\[?([^\]\n]+)\]?\s*(?:\(|$)'
    for match in re.finditer(list_pattern, content):
        title = match.group(1).strip()
        if title:
            titles.add(title)
    
    return titles

def dedupe_news(new_items: list, existing_file: str) -> list:
    """
    去重新闻条目
    new_items: [(title, content, source, ...)] 或 dict列表
    返回去重后的列表
    """
    existing = get_existing_titles(existing_file)
    
    result = []
    for item in new_items:
        if isinstance(item, dict):
            title = item.get('title', '')
        elif isinstance(item, (list, tuple)):
            title = item[0] if len(item) > 0 else ''
        else:
            title = str(item)
        
        if title and title not in existing:
            result.append(item)
            existing.add(title)  # 防止本次重复
    
    return result

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("用法: python3 news_dedupe.py <news_file>")
        print("输出已有标题列表（JSON格式）")
        sys.exit(1)
    
    import json
    titles = get_existing_titles(sys.argv[1])
    print(json.dumps(list(titles), ensure_ascii=False, indent=2))
