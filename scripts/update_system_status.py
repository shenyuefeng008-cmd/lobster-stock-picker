#!/usr/bin/env python3
"""
自动更新系统状态.json
在每日收盘后（15:30）执行，更新yesterday数据
"""
import json, sys
from pathlib import Path
from datetime import datetime

WS = Path(__file__).parent.parent
STATUS_FILE = WS / "trading/系统状态.json"

def update_system_status():
    """更新系统状态文件"""
    # 读取当前状态
    if STATUS_FILE.exists():
        status = json.loads(STATUS_FILE.read_text())
    else:
        status = {
            "_meta": {"version": 3, "purpose": "系统状态·统一文件"},
            "last_updated": "",
            "last_close_date": "",
            "yesterday": {"up_count": 0, "date": ""},
            "today": {"up_count": 0, "down_count": 0, "zt_count": 0, "dt_count": 0, "dimension": ""}
        }
    
    # 获取今日情绪数据
    try:
        sys.path.insert(0, str(WS / "scripts"))
        from get_market_sentiment import get_market_sentiment_legulegu
        up, down, zt, dt = get_market_sentiment_legulegu()
        
        if up < 0:  # 获取失败
            print("⚠️ 情绪数据获取失败，跳过更新")
            return
        
        # 判断维度
        if up < 1500:
            dimension = "冰点"
        elif up < 2000:
            dimension = "修复"
        elif up < 2500:
            dimension = "中性"
        elif up < 3500:
            dimension = "高潮"
        else:
            dimension = "极度高潮"
        
        status['today'] = {
            "up_count": up,
            "down_count": down,
            "zt_count": zt,
            "dt_count": dt,
            "dimension": dimension
        }
        
        # 更新yesterday（如果是收盘后）
        now = datetime.now()
        if now.hour >= 15:
            status['yesterday'] = {
                "up_count": up,
                "date": now.strftime('%Y-%m-%d')
            }
            status['last_close_date'] = now.strftime('%Y-%m-%d')
        
        status['last_updated'] = now.strftime('%Y-%m-%d')
        
        STATUS_FILE.write_text(json.dumps(status, ensure_ascii=False, indent=2))
        print(f"✅ 系统状态已更新: today={up}涨/{down}跌 dimension={dimension}")
        
    except Exception as e:
        print(f"❌ 更新失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == '__main__':
    update_system_status()
