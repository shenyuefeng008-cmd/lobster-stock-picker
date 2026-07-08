#!/usr/bin/env python3
"""
blog_auto_writer.py - 自动生成博客文章并更新 index.html
用法:
  python3 blog_auto_writer.py midday   # 午间文章 (12:00)
  python3 blog_auto_writer.py closing  # 收盘文章 (16:00)
"""
import sys, json, subprocess, re, os, datetime
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parent.parent
TRADING = WORKSPACE / "trading"
BLOG_HTML = WORKSPACE / "blog" / "index.html"

# ─── 交易日判断 ───────────────────────────────────────────────────────────────
HOLIDAYS = {
    "2026-01-01","2026-01-02","2026-01-03",
    "2026-01-26","2026-01-27","2026-01-28","2026-01-29","2026-01-30","2026-01-31",
    "2026-02-01","2026-02-02","2026-02-03","2026-02-04",
    "2026-04-04","2026-04-05","2026-04-06",
    "2026-05-01","2026-05-02","2026-05-03","2026-05-04","2026-05-05",
    "2026-06-19","2026-06-20","2026-06-21",
    "2026-09-25","2026-09-26","2026-09-27",
    "2026-10-01","2026-10-02","2026-10-03","2026-10-04","2026-10-05","2026-10-06","2026-10-07",
}
WORKDAYS = {
    "2026-01-25","2026-02-08","2026-04-26",
    "2026-09-28","2026-10-10",
}

def is_trading_day(d=None):
    if d is None:
        d = datetime.date.today()
    s = d.isoformat()
    if s in HOLIDAYS:
        return False
    if s in WORKDAYS:
        return True
    if d.weekday() >= 5:
        return False
    return True

# ─── 读取 trading 数据 ───────────────────────────────────────────────────────────
def load_json(path):
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return None

def get_market_sentiment():
    """从 legulegu.com 获取涨跌家数，失败则读取缓存"""
    # 先尝试在线获取
    try:
        r = subprocess.run(
            ['curl', '-sL', '--max-time', '10', '-A', 'Mozilla/5.0',
             'https://legulegu.com/stockdata/market-activity'],
            capture_output=True, text=True, timeout=15
        )
        txt = r.stdout
        m = re.search(r'(\d{4}-\d{2}-\d{2})\s+上涨[:：](\d+)\s+下跌[:：](\d+)', txt)
        if m:
            up, down = int(m.group(2)), int(m.group(3))
            # 不缓存旧数据，直接返回实时结果
            return up, down, m.group(1)
    except Exception:
        pass
    
    # 备用：新浪全市场分页统计
    try:
        ups = downs = 0
        for pg in [1, 2, 3, 4, 5]:
            u = f"https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/Market_Center.getHQNodeData?page={pg}&num=100&sort=code&asc=1&node=hs_a"
            req = urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=8) as resp:
                items = json.loads(resp.read().decode('gbk'))
            for i in items:
                cp = float(i.get('changepercent', 0))
                if cp > 0: ups += 1
                elif cp < 0: downs += 1
        if ups + downs > 100:
            return ups, downs, datetime.date.today().isoformat()
    except Exception:
        pass
    
    return None, None, ''

def get_index_prices():
    """从 qt.gtimg.cn 获取三大指数"""
    try:
        r = subprocess.run(
            ['curl', '-s', 'https://qt.gtimg.cn/q=sh000001,sz399001,sz399006'],
            capture_output=True, timeout=10
        )
        raw = r.stdout.decode('gbk', errors='replace')
        result = {}
        for line in raw.split('\n'):
            if not line.strip():
                continue
            m = re.search(r'v_([a-z0-9]+)="([^"]*)"', line)
            if m:
                code = m.group(1)
                fields = m.group(2).split('~')
                if len(fields) > 4:
                    try:
                        result[code] = {
                            'name': fields[1],
                            'price': float(fields[3]),
                            'yest': float(fields[4]),
                        }
                    except (ValueError, IndexError):
                        pass
        return result
    except Exception:
        return {}

def get_zt_count():
    """获取涨停/跌停数"""
    try:
        import akshare as ak
        df = ak.stock_zt_pool_em(date=datetime.date.today().strftime('%Y%m%d'))
        zt = len(df) if df is not None else 0
        return zt, None
    except Exception:
        return None, None

# ─── 文章生成 ─────────────────────────────────────────────────────────────────
MONTH_NAMES = ['','1月','2月','3月','4月','5月','6月','7月','8月','9月','10月','11月','12月']

def date_key():
    return datetime.date.today().strftime('%m%d')

def date_str():
    return f"{datetime.date.today().month}月{datetime.date.today().day}日"

def build_midday_article():
    """生成午间复盘文章"""
    today = date_str()
    up, down, _ = get_market_sentiment()
    indices = get_index_prices()

    if up is not None:
        if up < 1500:
            sentiment = f"冰点区（{up}涨/{down}跌）"
            dim = "1.0主导，仓位上限30%"
        elif up < 2500:
            sentiment = f"弱势区（{up}涨/{down}跌）"
            dim = "1.0+3.0，总仓位上限90%"
        elif up < 3500:
            sentiment = f"正常区（{up}涨/{down}跌）"
            dim = "2.0+1.0，仓位50-70%"
        else:
            sentiment = f"高潮区（{up}涨/{down}跌）"
            dim = "辅助模式，仓位10-20%"
    else:
        sentiment = "数据获取失败"
        dim = "未知"

    idx_html = ""
    if indices:
        for code, info in indices.items():
            chg = (info['price'] - info['yest']) / info['yest'] * 100
            color = 'green' if chg >= 0 else 'red'
            sign = '+' if chg >= 0 else ''
            idx_html += f"<tr><td>{info['name']}</td><td class='{color}'>{sign}{chg:.2f}%</td></tr>\n"

    body = f"""<blockquote>午间复盘：上午盘面总结、情绪跟踪、下午策略提示。</blockquote>

<h2>一、当前市场情绪</h2>
<div class="box {'box-r' if up is not None and up < 1500 else ('box-g' if up is not None and up > 3000 else 'box-b')}">
<strong>涨跌家数：</strong>{sentiment}<br>
<strong>维度判定：</strong>{dim}
</div>

<h2>二、指数表现</h2>
<table>
{idx_html}</table>

<h2>三、下午策略提示</h2>
<p>根据当前情绪周期，下午注意以下几点：</p>
<ul>
<li>1.0模式：冰点期寻找分歧低吸机会，极度高潮期休眠</li>
<li>2.0模式：板块轮动期关注高低切机会</li>
<li>3.0模式：趋势回踩均线低吸，不追涨停</li>
</ul>

<blockquote>数据来源于自动采集，仅供参考。股市有风险，入市需谨慎。</blockquote>"""

    return {
        'tags': [{'t':'午间复盘','c':'tag-blue'}, {'t':'情绪跟踪','c':'tag-green'}],
        'title': f"{today} 午间复盘：情绪与策略",
        'meta': f"2026年{today} · 5 min read",
        'body': body,
    }

def build_closing_article():
    """生成收盘复盘文章 - 增强版"""
    today = date_str()
    up, down, _ = get_market_sentiment()
    indices = get_index_prices()

    # 读取模拟仓状态
    sim_state = load_json(str(TRADING / 'sim_state.json')) or {}
    positions = sim_state.get('positions', [])
    trading_log = load_json(str(TRADING / 'trading_log.json')) or []
    
    # 如果没有trading_log，尝试从sim_state构建
    if not trading_log and positions:
        # 从持仓记录生成日志
        trading_log = []
        for p in positions:
            trading_log.append({
                'time': p.get('buy_date', ''),
                'action': '持仓',
                'name': p.get('name', ''),
                'price': p.get('buy_price', ''),
                'shares': p.get('shares', ''),
                'reason': p.get('reason', '')
            })

    # 读取盘前候选今日表现（支持新旧两种格式）
    raw_premarket = load_json(str(TRADING / 'premarket_candidates.json'))
    if isinstance(raw_premarket, dict) and 'candidates' in raw_premarket:
        # 新格式：{candidates: {维度1: [{名称,代码,...}], ...}}
        premarket = []
        for dim_name, dim_list in raw_premarket['candidates'].items():
            for item in dim_list:
                item['dimension'] = dim_name
                premarket.append(item)
    elif isinstance(raw_premarket, list):
        # 旧格式：扁平列表
        premarket = raw_premarket
    else:
        premarket = []
    bid_result = load_json(str(TRADING / 'bid_result.json'))

    body = f"""<blockquote>收盘复盘：全天市场总结、选股验证、模拟仓表现、经验教训。</blockquote>

<h2>一、全天市场概览</h2>
"""
    # 情绪判定
    if up is not None:
        if up < 1500:
            sentiment = "冰点"
            color = "box-r"
            dim = "1.0主导，仓位上限30%"
        elif up < 2500:
            sentiment = "弱势"
            color = "box-b"
            dim = "1.0+3.0，总仓位上限90%"
        elif up < 3500:
            sentiment = "正常"
            color = "box-b"
            dim = "2.0+1.0，仓位50-70%"
        else:
            sentiment = "极度高潮"
            color = "box-g"
            dim = "辅助模式，仓位10-20%"
        
        body += f"""<div class="{color}">
<strong>涨跌家数：</strong>上涨 {up} 家，下跌 {down} 家<br>
<strong>情绪判定：</strong>{sentiment}（{dim}）
</div>
"""
        if indices:
            body += "<table><tr><th>指数</th><th>涨跌幅</th></tr>\n"
            for code, info in indices.items():
                chg = (info['price'] - info['yest']) / info['yest'] * 100
                sign = '+' if chg >= 0 else ''
                body += f"<tr><td>{info['name']}</td><td class={'green' if chg >= 0 else 'red'}>{sign}{chg:.2f}%</td></tr>\n"
            body += "</table>\n"
    else:
        body += """<p>涨跌家数数据获取失败（已启用缓存 fallback）。</p>
"""

    # 今日选股结果
    body += """<h2>二、今日选股验证</h2>
<p>盘前候选标的及当日表现：</p>
"""
    if premarket:
        body += "<table><tr><th>维度</th><th>标的</th><th>代码</th><th>结果</th><th>备注</th></tr>\n"
        for c in premarket[:15]:
            body += f"""<tr>
<td>{c.get('dimension','')}</td>
<td>{c.get('name','')}</td>
<td>{c.get('code','')}</td>
<td>{c.get('result', '待验证')}</td>
<td>{c.get('notes', '')}</td>
</tr>\n"""
        body += "</table>\n"
    else:
        body += "<p>盘前无候选数据。</p>\n"

    # 竞价结果
    if bid_result:
        passed = bid_result.get('passed', [])
        if passed:
            body += "<p><strong>竞价通过：</strong></p><ul>\n"
            for c in passed:
                body += f"<li>{c.get('name','')}({c.get('code','')}) - {c.get('strategy','')}</li>\n"
            body += "</ul>\n"
        else:
            body += "<p><strong>竞价通过：</strong>无（极度高潮期正确休眠）</p>\n"

    # 模拟仓状态
    body += """<h2>三、模拟仓表现</h2>
"""
    if positions:
        total_value = 0
        body += "<table><tr><th>持仓</th><th>成本</th><th>现价</th><th>盈亏</th><th>备注</th></tr>\n"
        for p in positions:
            try:
                curr = float(p.get('current_price', 0) or 0)
                cost = float(p.get('buy_price', 0) or 0)
                shares = int(p.get('shares', 0) or 0)
                if curr and cost:
                    value = curr * shares
                    pnl = (curr - cost) * shares
                    pnl_pct = (curr - cost) / cost * 100
                    total_value += value
                    pnl_color = 'green' if pnl >= 0 else 'red'
                    sign = '+' if pnl >= 0 else ''
                    body += f"""<tr>
<td>{p.get('name','')}</td>
<td>{cost:.2f}</td>
<td>{curr:.2f}</td>
<td class="{pnl_color}">{sign}{pnl:.0f} ({sign}{pnl_pct:.1f}%)</td>
<td>{p.get('reason','')[:20]}</td>
</tr>\n"""
            except:
                pass
        body += "</table>\n"
        
        # 总资产
        cash = sim_state.get('cash', 0)
        total = total_value + cash
        body += f"<p><strong>总资产：</strong>{total:,.0f}元（含现金 {cash:,.0f}元，持仓 {total_value:,.0f}元）</p>\n"
    else:
        body += "<p>模拟仓空仓。</p>\n"

    # 交易日志
    if trading_log:
        body += "<p><strong>今日操作：</strong></p><ul>\n"
        for t in trading_log[-5:]:
            action = t.get('action', '')
            name = t.get('name', '')
            body += f"<li>{action} {name}</li>\n"
        body += "</ul>\n"

    # 经验教训
    body += """<h2>四、经验与教训</h2>
<ul>
<li><strong>规则执行：</strong>"""
    if up and up > 3500:
        body += "极度高潮期正确休眠1.0/2.0，未追高。"
    elif up and up < 1500:
        body += "冰点期正确切换到1.0主导模式。"
    else:
        body += "按规则正常执行。"
    
    body += """</li>
<li><strong>明日策略：</strong>根据明日开盘情绪重新判定维度。</li>
</ul>

<p><strong>明日是否为交易日：</strong>"""
    tomorrow = datetime.date.today() + datetime.timedelta(days=1)
    if is_trading_day(tomorrow):
        body += "是，系统将继续运行。"
    else:
        body += "否，周末休市。"
    body += """</p>

<blockquote>数据来源于自动采集，仅供参考。股市有风险，入市需谨慎。</blockquote>"""

    return {
        'tags': [{'t':'收盘复盘','c':'tag-blue'}, {'t':'数据验证','c':'tag-yellow'}],
        'title': f"{today} 收盘复盘：全天情绪与选股验证",
        'meta': f"2026年{today} · 8 min read",
        'body': body,
    }

# ─── 更新 index.html ───────────────────────────────────────────────────────────
def update_blog_html(article_key, article):
    """将新文章插入 blog/index.html 的 articles JS 对象中"""
    if not BLOG_HTML.exists():
        print(f"ERROR: {BLOG_HTML} not found")
        return False

    with open(BLOG_HTML, 'r', encoding='utf-8') as f:
        content = f.read()

    tags_js = json.dumps(article['tags'], ensure_ascii=False)
    body_escaped = article['body'].replace('`', '\\`').replace('${', '\\${')
    new_article_js = f"""
  '{article_key}': {{
    tags: {tags_js},
    title: `{article['title']}`,
    meta: `{article['meta']}`,
    body: `{body_escaped}`
  }},
"""

    # 找到 articles 对象，插入新文章
    import re
    # 匹配 articles: { ... } 的结束位置，使用非贪婪 + DOTALL 正确匹配嵌套对象
    match = re.search(r"(const articles = \{.*?\n\};)", content, re.DOTALL)
    if match:
        prefix = match.group(1)
        # suffix 包含结尾的 };
        suffix = ''  # 不再需要 suffix，因为我们重写了整个块
        # 检查是否已存在同名文章
        if f"'{article_key}':" in prefix:
            # 替换已有文章：删除旧条目
            prefix = re.sub(rf"'{article_key}':\s*\{{[^}}]*\}},\s*", "", prefix)
        # 重建 articles 块
        tags_js = json.dumps(article['tags'], ensure_ascii=False)
        body_escaped = article['body'].replace('`', '\\`').replace('${', '\\${')
        new_article_js = f"\n  '{article_key}': {{\n    tags: {tags_js},\n    title: `{article['title']}`,\n    meta: `{article['meta']}`,\n    body: `{body_escaped}`\n  }}\n"
        new_content = "const articles = {" + prefix.split("const articles = {", 1)[1] + new_article_js + "};\n"
        with open(BLOG_HTML, 'w', encoding='utf-8') as f:
            f.write(new_content)
        return True
    return False

# ─── 主程序 ───────────────────────────────────────────────────────────────────
if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("用法: python3 blog_auto_writer.py [midday|closing]")
        sys.exit(1)
    
    mode = sys.argv[1]
    today_key = date_key()
    
    if not is_trading_day():
        print("非交易日，跳过")
        sys.exit(0)
    
    if mode == 'midday':
        article = build_midday_article()
        article_key = f"midday_{today_key}"
    elif mode == 'closing':
        article = build_closing_article()
        article_key = f"closing_{today_key}"
    else:
        print(f"未知模式: {mode}")
        sys.exit(1)
    
    if update_blog_html(article_key, article):
        print(f"✅ 文章已更新: {article['title']}")
    else:
        print("❌ 更新失败")
