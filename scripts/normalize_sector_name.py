#!/usr/bin/env python3
"""
板块名称标准化工具
将不同叫法的板块名称统一为产业逻辑框架中的标准名称
"""

import json
from pathlib import Path

def normalize_sector_name(name, mapping_file=None):
    """
    标准化板块名称
    
    Args:
        name: 原始板块名称
        mapping_file: 映射文件路径（默认：trading/sector_name_mapping.json）
    
    Returns:
        标准化后的名称（如果找不到映射，返回原始名称）
    """
    if mapping_file is None:
        mapping_file = Path(__file__).parent.parent / 'trading' / 'sector_name_mapping.json'
    
    if not Path(mapping_file).exists():
        return name
    
    with open(mapping_file) as f:
        mapping = json.load(f)
    
    # 遍历映射表
    for standard_name, aliases in mapping.get('映射表', {}).items():
        if name in aliases or name == standard_name:
            return standard_name
    
    # 没找到映射，返回原始名称
    return name


def filter_pending_tracks(new_tracks, framework_text, mapping_file=None):
    """
    过滤出新赛道（不在框架中且经过标准化）
    
    Args:
        new_tracks: 检测到的板块列表
        framework_text: 产业逻辑框架.md的文本内容
        mapping_file: 映射文件路径
    
    Returns:
        待审核赛道列表（已标准化）
    """
    pending = []
    normalized_map = {}  # 原始名称 -> 标准化名称
    
    for track in new_tracks:
        normalized = normalize_sector_name(track, mapping_file)
        normalized_map[track] = normalized
        
        # 检查标准化后的名称是否在框架中
        if normalized not in framework_text:
            pending.append({
                'original': track,
                'normalized': normalized,
                'reason': f'标准化: {track} → {normalized}' if track != normalized else '新赛道'
            })
    
    return pending, normalized_map


if __name__ == '__main__':
    # 测试
    test_names = ['AI', '人工智能AI', '液冷散热', 'IDC', 'HBM']
    
    print('板块名称标准化测试：')
    for name in test_names:
        normalized = normalize_sector_name(name)
        print(f'  {name} → {normalized}')
    
    print('\n完成')
