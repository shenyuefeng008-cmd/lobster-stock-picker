#!/usr/bin/env python3
"""
lobster_lexiang_sync.py — 龙虾系统数据每日同步到腾讯乐享
由 cron 每日 02:00 触发

依赖: mcporter CLI (乐享 MCP 已配置)
写入规则（乐享协作规范）：
  1. 本地维护 entry_map.json（标题→entry_id 映射）
  2. 同步时先查映射 → 有 entry_id 则 update，无则 create 并写入映射
  3. 更新前先读现有内容（符合「写前先读」规范）
"""

import subprocess, json, os, glob
from datetime import datetime

WORKSPACE = "/Users/yuefengshen/.qclaw/workspace-1gwpiwf3hr163jz5"
SPACE_ID = "1353939a48bc4183bc8340cd28e7d3e7"
RESULT_ID = "d079e7d1d0b648769019a123992fca66"   # 结果汇总

# 目录 entry_id
FOLDER_龙虾系统 = "d4f02352c1f04380b0ea193ceb46c263"
FOLDER_运行数据 = "8e152ecd38584cf995079611cb0ba221"
FOLDER_系统文档 = "bb319f4495f546c08af1337d1c1b79e4"

ENTRY_MAP_PATH = f"{WORKSPACE}/trading/lexiang_entry_map.json"

DATE = datetime.now().strftime("%Y-%m-%d")
DATE_SHORT = datetime.now().strftime("%m-%d")

# ── 工具函数 ──────────────────────────────────────────────────

def log(msg):
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)

def mcporter_raw(tool, args_dict, timeout=30):
    args_json = json.dumps(args_dict, ensure_ascii=False)
    r = subprocess.run(
        ["mcporter", "call", "lexiang", tool, "--args", args_json],
        capture_output=True, text=True, timeout=timeout
    )
    return r.returncode, r.stdout.strip(), r.stderr.strip()

def read_local_file(path, max_chars=350000):
    try:
        with open(path, 'r', encoding='utf-8') as f:
            text = f.read()
        if len(text) > max_chars:
            text = text[:max_chars] + "\n\n...(内容截断)"
        return text.strip()
    except FileNotFoundError:
        return None
    except Exception as e:
        log(f"  ⚠️  读取失败: {e}")
        return None

def load_entry_map():
    """加载本地 entry_id 映射 {title: entry_id}"""
    if os.path.exists(ENTRY_MAP_PATH):
        try:
            with open(ENTRY_MAP_PATH, 'r') as f:
                return json.load(f)
        except Exception:
            pass
    return {}

def save_entry_map(m):
    with open(ENTRY_MAP_PATH, 'w') as f:
        json.dump(m, f, ensure_ascii=False, indent=2)

# ── 乐享读写 ──────────────────────────────────────────────────

def read_lexiang_entry(entry_id):
    """读现有内容（协作规范：写前先读）"""
    rc, out, err = mcporter_raw("block_fetch_page", {"entry_id": entry_id})
    if rc == 0 and out:
        return out
    return None

def create_entry(title, content, parent_id):
    """创建新文档，返回 entry_id"""
    args = {
        "name": title,
        "content_type": "markdown",
        "space_id": SPACE_ID,
        "parent_id": parent_id,
        "content": content
    }
    rc, out, err = mcporter_raw("entry_import_content", args)
    if rc == 0 and out:
        try:
            data = json.loads(out)
            return data.get("entry", {}).get("id")
        except Exception:
            pass
    log(f"  ❌ 创建失败: {err[:100]}")
    return None

def update_entry(entry_id, content):
    """
    全量替换（乐享协作规范）
    先用 block_fetch_page 读现有内容，再用 entry_import_content_to_entry force_write 替换
    """
    # 写前先读（规范步骤）
    old = read_lexiang_entry(entry_id)
    if old is not None:
        log(f"  📖 已读现有内容 ({len(old)}字符)")

    rc, out, err = mcporter_raw("entry_import_content_to_entry", {
        "entry_id": entry_id,
        "content": content,
        "content_type": "markdown",
        "force_write": True
    })
    if rc == 0:
        return True
    log(f"  ❌ 更新失败: {err[:120]}")
    return False

def sync_one(label, local_path, title, parent_id, entry_map):
    """
    同步单个文件：
      1. 读本地文件
      2. 查 entry_map 是否有 entry_id
      3. 有 → update_entry；无 → create_entry 并写入 map
    """
    content = read_local_file(local_path)
    if content is None:
        log(f"  ⚠️  跳过 {label} — 文件不存在: {local_path}")
        return "skip"

    entry_id = entry_map.get(title)

    if entry_id:
        log(f"  🔄 命中映射 → 全量更新 ({title})")
        ok = update_entry(entry_id, content)
        if ok:
            log(f"  ✅ {label} 更新成功")
            return "updated"
        else:
            log(f"  ⚠️  更新失败，尝试创建新版本")
            new_id = create_entry(title, content, parent_id)
            if new_id:
                entry_map[title] = new_id
                log(f"  ✅ {label} 创建新版本成功 ({new_id[:12]}...)")
                return "created"
            return "failed"
    else:
        log(f"  🆕 无映射 → 创建新文档 ({title})")
        new_id = create_entry(title, content, parent_id)
        if new_id:
            entry_map[title] = new_id
            log(f"  ✅ {label} 创建成功 ({new_id[:12]}...)")
            return "created"
        else:
            log(f"  ❌ {label} 创建失败")
            return "failed"

# ── 主流程 ─────────────────────────────────────────────────────

def sync_all():
    log(f"🦞 龙虾系统 → 腾讯乐享 同步开始 ({DATE})")
    entry_map = load_entry_map()
    results = []

    # 1. 新闻资讯（按日期，每次新建）
    news_path = f"{WORKSPACE}/trading/news/{DATE}.md"
    news_title = f"龙虾-{DATE_SHORT}-新闻资讯"
    r = sync_one("新闻资讯", news_path, news_title,
                 FOLDER_龙虾系统, entry_map)
    results.append(f"新闻资讯: {r}")

    # 2. 催化日历（最新版，更新模式）
    cat_path = f"{WORKSPACE}/trading/催化日历.md"
    cat_title = "龙虾-最新-催化日历"
    r = sync_one("催化日历", cat_path, cat_title,
                 FOLDER_运行数据, entry_map)
    results.append(f"催化日历: {r}")

    # 3. 趋势容量池
    pool_path = f"{WORKSPACE}/trading/趋势容量池.md"
    pool_title = "龙虾-最新-趋势容量池"
    r = sync_one("趋势容量池", pool_path, pool_title,
                 FOLDER_运行数据, entry_map)
    results.append(f"趋势容量池: {r}")

    # 4. 交易追踪
    track_path = f"{WORKSPACE}/trading/交易追踪.md"
    track_title = "龙虾-最新-交易追踪"
    r = sync_one("交易追踪", track_path, track_title,
                 FOLDER_运行数据, entry_map)
    results.append(f"交易追踪: {r}")

    # 5. 工作日志（按日期，每次新建）
    worklog_path = f"{WORKSPACE}/memory/{DATE}.md"
    worklog_title = f"龙虾-{DATE_SHORT}-工作日志"
    if os.path.exists(worklog_path):
        r = sync_one("工作日志", worklog_path, worklog_title,
                     FOLDER_龙虾系统, entry_map)
    else:
        r = "skip(无文件)"
    results.append(f"工作日志: {r}")

    # 6. 产业图谱
    sector_path = f"{WORKSPACE}/trading/产业图谱.md"
    sector_title = f"龙虾-{DATE_SHORT}-产业图谱"
    r = sync_one("产业图谱", sector_path, sector_title,
                 FOLDER_系统文档, entry_map)
    results.append(f"产业图谱: {r}")

    # 7. 进化日志（最新一份）
    evo_glob = f"{WORKSPACE}/trading/reports/evolution_*.md"
    evo_files = sorted(glob.glob(evo_glob), key=os.path.getmtime, reverse=True)
    if evo_files:
        evo_date = os.path.basename(evo_files[0]).replace('evolution_', '').replace('.md', '')
        evo_title = f"龙虾-{evo_date}-进化日志"
        r = sync_one("进化日志", evo_files[0], evo_title,
                     FOLDER_龙虾系统, entry_map)
    else:
        r = "skip(无文件)"
    results.append(f"进化日志: {r}")

    # 8. 选股历史
    sel_today = f"{WORKSPACE}/trading/选股历史-{DATE}.md"
    sel_latest = f"{WORKSPACE}/trading/选股历史.md"
    sel_path = sel_today if os.path.exists(sel_today) else sel_latest
    if os.path.exists(sel_path):
        sel_title = f"龙虾-{DATE}-选股历史"
        r = sync_one("选股历史", sel_path, sel_title,
                     FOLDER_龙虾系统, entry_map)
    else:
        r = "skip(无文件)"
    results.append(f"选股历史: {r}")

    # 9. 关注股
    watch_path = f"{WORKSPACE}/trading/关注股.md"
    watch_title = "龙虾-最新-关注股"
    r = sync_one("关注股", watch_path, watch_title,
                 FOLDER_运行数据, entry_map)
    results.append(f"关注股: {r}")

    # 保存映射
    save_entry_map(entry_map)
    log(f"💾 映射已保存 ({len(entry_map)} 条)")

    # 写入结果汇总
    summary = " | ".join(results)
    log(f"📊 同步完成: {summary}")
    write_result(summary, results)

def write_result(summary, results):
    NOW = datetime.now().strftime("%Y-%m-%d %H:%M")
    detail = "\n".join(f"- {r}" for r in results)
    content = f"""## [龙虾同步] {DATE} 执行报告

- **执行人**: 龙虾超短交易系统（自动cron）
- **完成时间**: {NOW}
- **执行结果**: ✅ 完成
- **结果摘要**: {summary}
- **详细内容**:
{detail}
"""
    rc, out, err = mcporter_raw("entry_import_content_to_entry", {
        "entry_id": RESULT_ID,
        "content": content,
        "content_type": "markdown"
    })
    if rc == 0:
        log("  📊 结果已写入乐享结果汇总")
    else:
        log(f"  ⚠️  结果汇总写入失败: {err[:100]}")

if __name__ == "__main__":
    sync_all()
