#!/usr/bin/env python3
"""
wechat_publisher_v2.py - 公众号文章发布工具 (v2 接入 baoyu-md 渲染)
 
功能：
  1. 读取 Markdown 文章（含 YAML front matter）
  2. 使用 baoyu-md 渲染为排好版的 HTML（自动内联 CSS）
  3. 上传图片到公众号素材库
  4. 推送到草稿箱或直接发布

用法：
  python3 wechat_publisher_v2.py --source article.md          # 推草稿箱
  python3 wechat_publisher_v2.py --source article.md --mode publish  # 直接发布
  python3 wechat_publisher_v2.py --source blog/closes/2026-05-25.html  # 兼容旧 HTML

配置：
  .env 或环境变量: WECHAT_APPID, WECHAT_APPSECRET
  ~/.baoyu-skills/baoyu-post-to-wechat/EXTEND.md  (作者名等配置)
"""

import os
import re
import json
import sys
import subprocess
import tempfile
import mimetypes
import time
from pathlib import Path
from datetime import datetime

# ─── 路径 ──────────────────────────────────────────────────────────────────
WORKSPACE = Path(__file__).resolve().parent.parent
BAOYU_POST = Path.home() / ".baoyu-skills" / "baoyu-post-to-wechat"
BAOYU_MD = Path.home() / ".bun" / "install" / "cache" / \
    "baoyu-md@0.1.0@@registry.npmmirror.com@@@1"

ENV_FILE = Path.home() / ".baoyu-skills" / ".env"
EXTEND_FILE = BAOYU_POST / "EXTEND.md"
CACHE_TOKEN = WORKSPACE / ".wechat_token.json"

# ─── 凭证 ──────────────────────────────────────────────────────────────────
def load_env():
    """从 baoyu 的 .env 加载微信凭证"""
    env = {}
    for f in [ENV_FILE]:
        if f.exists():
            for line in f.read_text().strip().split("\n"):
                line = line.strip()
                if "=" in line and not line.startswith("#"):
                    k, v = line.split("=", 1)
                    env[k.strip()] = v.strip()
    # 环境变量优先
    env["WECHAT_APPID"] = os.environ.get("WECHAT_APPID", env.get("WECHAT_APP_ID", ""))
    env["WECHAT_APPSECRET"] = os.environ.get("WECHAT_APPSECRET", env.get("WECHAT_APP_SECRET", ""))
    return env

def load_extend():
    """加载 baoyu-post-to-wechat 的扩展配置"""
    config = {}
    if EXTEND_FILE.exists():
        for line in EXTEND_FILE.read_text().strip().split("\n"):
            line = line.strip()
            if ":" in line and not line.startswith("#"):
                k, v = line.split(":", 1)
                config[k.strip()] = v.strip()
    return config

# ─── 免责声明模板 ──────────────────────────────────────────────────────────
DISCLAIMER_HTML = """
<div style="background:#fff3e0;border-left:4px solid #ff9800;padding:16px 20px;margin:24px 0;border-radius:4px">
<strong>⚠️ 风险提示</strong><br/>
本公众号所有内容仅作为个人交易系统的研究与记录，不构成任何投资建议。
投资者据此操作，风险自担。A股市场有风险，入市需谨慎。
</div>
"""

DISCLAIMER_MD = """
> **⚠️ 风险提示**
> 本公众号所有内容仅作为个人交易系统的研究与记录，不构成任何投资建议。
> 投资者据此操作，风险自担。A股市场有风险，入市需谨慎。
"""

# ─── 微信公众号 API ──────────────────────────────────────────────────────
class WeChatAPI:
    def __init__(self, appid, appsecret):
        self.appid = appid
        self.appsecret = appsecret
        self.base_url = "https://api.weixin.qq.com/cgi-bin"
        self._token = None
        self._token_expires = 0

    def get_token(self) -> str:
        now = time.time()
        if self._token and now < self._token_expires - 60:
            return self._token
        # 缓存
        if CACHE_TOKEN.exists():
            try:
                data = json.loads(CACHE_TOKEN.read_text())
                if data.get("expires_at", 0) > now + 60:
                    self._token = data["access_token"]
                    self._token_expires = data["expires_at"]
                    return self._token
            except:
                pass
        # 刷新
        url = f"{self.base_url}/token?grant_type=client_credential&appid={self.appid}&secret={self.appsecret}"
        r = subprocess.run(["curl", "-s", url], capture_output=True, text=True, timeout=15)
        result = json.loads(r.stdout)
        if "access_token" in result:
            self._token = result["access_token"]
            self._token_expires = now + result.get("expires_in", 7200)
            CACHE_TOKEN.write_text(json.dumps({
                "access_token": self._token,
                "expires_at": self._token_expires
            }))
            return self._token
        raise Exception(f"Token 获取失败: {result}")

    def upload_image(self, image_path: str) -> dict:
        """上传永久图片素材"""
        token = self.get_token()
        url = f"{self.base_url}/material/add_material?access_token={token}&type=image"
        mime = mimetypes.guess_type(image_path)[0] or "image/png"
        cmd = ["curl", "-s", "-F", f"media=@{image_path};type={mime}", url]
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        result = json.loads(r.stdout)
        if "media_id" in result:
            print(f"[✓] 图片上传成功: {Path(image_path).name} -> {result['media_id']}")
        else:
            print(f"[✗] 图片上传失败: {result}")
        return result

    def add_draft(self, articles: list) -> dict:
        payload = {"articles": articles}
        body = json.dumps(payload, ensure_ascii=False)
        url = f"{self.base_url}/draft/add?access_token={self.get_token()}"
        r = subprocess.run(
            ["curl", "-s", "-X", "POST", url,
             "-H", "Content-Type: application/json; charset=utf-8",
             "-d", body],
            capture_output=True, text=True, timeout=30
        )
        result = json.loads(r.stdout)
        if result.get("errcode", 0) == 0:
            print(f"[✓] 草稿添加成功! media_id: {result.get('media_id')}")
        else:
            print(f"[✗] 草稿添加失败: {result}")
        return result

# ─── 渲染引擎 ─────────────────────────────────────────────────────────────
def render_via_baoyu_md(markdown_content: str, extend_config: dict = None) -> str:
    """
    使用 baoyu-md 将 Markdown 渲染为内联 CSS 的 HTML
    
    流程：
      1. 写入临时 .md 文件
      2. 用 Node.js 调用 baoyu-md 的 renderMarkdownDocument
      3. 返回渲染后的 HTML（CSS 已内联）
    """
    task = """
const path = require('path');
const baoyuMd = require('%s');

(async () => {
  const fs = require('fs');
  const input = fs.readFileSync('%s', 'utf-8');
  
  const options = {
    theme: '%s',
    primaryColor: '%s',
    fontFamily: '%s',
    fontSize: '%s',
    keepTitle: true,
    codeTheme: 'github',
    isMacCodeBlock: false
  };
  
  try {
    const result = await baoyuMd.renderMarkdownDocument(input, options);
    // 返回内联 CSS 后的完整 HTML
    console.log('===BAOYU_OUTPUT_START===');
    console.log(result.html);
    console.log('===BAOYU_OUTPUT_END===');
    console.log('===META_START===');
    console.log(JSON.stringify(result.meta));
    console.log('===META_END===');
  } catch (e) {
    console.error(e);
    process.exit(1);
  }
})();
"""
    # 写入临时 MD
    with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False, encoding='utf-8') as f:
        f.write(markdown_content)
        temp_md = f.name

    baoyu_dist = str(BAOYU_MD / "dist" / "index.cjs")
    if not os.path.exists(baoyu_dist):
        # 尝试 index.js
        baoyu_dist = str(BAOYU_MD / "dist" / "index.js")

    script_content = task % (
        baoyu_dist.replace('\\', '\\\\'),
        temp_md.replace('\\', '\\\\'),
        extend_config.get('default_theme', 'default') if extend_config else 'default',
        extend_config.get('default_color', '#c0392b') if extend_config else '#c0392b',
        'sans-serif',
        '16px'
    )

    with tempfile.NamedTemporaryFile(mode='w', suffix='.js', delete=False, encoding='utf-8') as f:
        f.write(script_content)
        temp_js = f.name

    try:
        r = subprocess.run(
            ["/usr/local/bin/node", temp_js],
            capture_output=True, text=True, timeout=30
        )
        if r.returncode != 0:
            print(f"[!] baoyu-md 渲染失败: {r.stderr}")
            # 降级：直接返回 markdown 的简单 HTML 转换
            return fallback_render(markdown_content)
        
        # 提取输出
        out = r.stdout
        m = re.search(r'===BAOYU_OUTPUT_START===\n(.*?)\n===BAOYU_OUTPUT_END===', out, re.DOTALL)
        if m:
            html = m.group(1)
            print(f"[✓] baoyu-md 渲染成功 ({len(html)} bytes)")
            html = tighten_for_wechat(html)
            print(f"[→] WeChat 格式适配完成")
            return html
        else:
            print(f"[!] 无法解析 baoyu-md 输出，降级渲染")
            return fallback_render(markdown_content)
    finally:
        os.unlink(temp_md)
        os.unlink(temp_js)


def tighten_for_wechat(html: str) -> str:
    """
    针对公众号移动端阅读，收窄 baoyu-md 过大的间距。
    """
    # 1. h2 标题间距：4em auto 2em → 1.5em auto 0.8em
    html = html.replace('margin: 4em auto 2em', 'margin: 1.5em auto 0.8em')
    # 2. h3 标题间距：2em 8px 0.75em → 1.2em 8px 0.5em
    html = html.replace('margin: 2em 8px 0.75em', 'margin: 1.2em 8px 0.5em')
    # 3. p 段落间距：1.5em 8px → 0.8em 8px
    html = html.replace('margin: 1.5em 8px', 'margin: 0.8em 8px')
    # 4. blockquote 下边距、hr 间距
    html = html.replace('margin-bottom: 1em;', 'margin-bottom: 0.5em;')
    # 5. h4 间距
    html = html.replace('margin: 2em 8px 0.5em', 'margin: 1em 8px 0.3em')
    # 6. h1 间距
    html = html.replace('margin: 2em auto 1em', 'margin: 1.5em auto 0.8em')
    return html


def fallback_render(markdown_content: str) -> str:
    """
    降级渲染：当 baoyu-md 不可用时，用 Python 简单转换
    """
    html = markdown_content
    # 标题转换
    html = re.sub(r'^# (.+)$', r'<h1>\1</h1>', html, flags=re.MULTILINE)
    html = re.sub(r'^## (.+)$', r'<h2>\1</h2>', html, flags=re.MULTILINE)
    html = re.sub(r'^### (.+)$', r'<h3>\1</h3>', html, flags=re.MULTILINE)
    html = re.sub(r'^#### (.+)$', r'<h4>\1</h4>', html, flags=re.MULTILINE)
    # 加粗/斜体
    html = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', html)
    html = re.sub(r'\*(.+?)\*', r'<em>\1</em>', html)
    # 无序列表
    html = re.sub(r'^- (.+)$', r'<li>\1</li>', html, flags=re.MULTILINE)
    html = re.sub(r'(<li>.*?</li>(\s*<li>.*?</li>)*)', r'<ul>\1</ul>', html, flags=re.DOTALL)
    # 段落
    html = re.sub(r'\n\n', r'</p><p>', html)
    html = f'<p>{html}</p>'
    # 表格等复杂格式无法处理，直接保留原文本
    print(f"[!] 降级渲染完成（纯 Markdown 转换，无 CSS 内联）")
    return html


def strip_yaml_frontmatter(markdown: str) -> str:
    """移除 YAML front matter，返回纯净 Markdown"""
    m = re.match(r'^---\s*\n(.*?)\n---\s*\n', markdown, re.DOTALL)
    if m:
        return markdown[m.end():]
    return markdown


# ─── 公众号文章构建 ──────────────────────────────────────────────────────
def build_wx_article(source_path: str) -> dict:
    """
    根据源文件构建公众号文章
    
    支持：
      - .md  → baoyu-md 渲染
      - .html → 直接使用（兼容旧格式）
    """
    env = load_env()
    extend = load_extend()
    
    source = Path(source_path)
    content_raw = source.read_text(encoding='utf-8')
    
    if source.suffix.lower() == '.md':
        # 提取 front matter 的 title
        title = ""
        m = re.match(r'^---\s*\n(.*?)\n---', content_raw, re.DOTALL)
        if m:
            yaml_block = m.group(1)
            title_m = re.search(r'^title:\s*(.+)$', yaml_block, re.MULTILINE)
            if title_m:
                title = title_m.group(1).strip().strip('"').strip("'")
        
        # 渲染 Markdown → HTML（带内联 CSS）
        markdown_body = strip_yaml_frontmatter(content_raw)
        # 追加免责声明
        markdown_body += "\n\n" + DISCLAIMER_MD
        html = render_via_baoyu_md(markdown_body, extend)
        
        if not title:
            # 从 h1 提取
            m = re.search(r'<h1[^>]*>(.*?)</h1>', html)
            title = m.group(1).strip() if m else "龙虾选股日报"
        
        # 从 baoyu-md 输出提取正文（去除 <html>/<head>/<body> 壳）
        body_m = re.search(r'<div id="output">(.*?)</div>', html, re.DOTALL)
        body_html = body_m.group(1).strip() if body_m else html
        
    elif source.suffix.lower() == '.html':
        # 兼容旧 HTML 格式
        m = re.search(r'<h1[^>]*>(.*?)</h1>', content_raw)
        title = m.group(1).strip() if m else "龙虾选股日报"
        body_html = content_raw
        # 移除已有的免责
        body_html = re.sub(r'<div[^>]*background:#fff3e0[^>]*>.*?</div>', '', body_html, flags=re.DOTALL)
        body_html += DISCLAIMER_HTML
    else:
        raise ValueError(f"不支持的格式: {source.suffix}")
    
    # 添加 WeChat 兼容的包装
    author = extend.get('default_author', '峰峰火火红红红')
    digest = re.sub(r'<[^>]+>', '', body_html)[:54].strip() + "…" if re.sub(r'<[^>]+>', '', body_html).strip() else ""
    
    # 检查封面图
    thumb_media_id = ""
    cover_path = WORKSPACE / "trading" / "cover_uploaded.txt"
    if cover_path.exists():
        thumb_media_id = cover_path.read_text().strip()
    
    articles = [{
        "title": title,
        "author": author,
        "digest": digest[:60],
        "content": body_html,
        "content_source_url": "",
        "thumb_media_id": thumb_media_id,
        "need_open_comment": int(extend.get('need_open_comment', '1')),
        "only_fans_can_comment": int(extend.get('only_fans_can_comment', '0')),
    }]
    
    return {
        "articles": articles,
        "title": title,
        "body_length": len(body_html)
    }


# ─── 主入口 ────────────────────────────────────────────────────────────────
def main():
    import argparse
    parser = argparse.ArgumentParser(description="龙虾选股公众号发布工具 v2")
    parser.add_argument("--source", required=True, help="源文件 (.md 或 .html)")
    parser.add_argument("--mode", choices=["draft", "publish"], default="draft",
                        help="draft=推草稿箱, publish=直接发布")
    parser.add_argument("--cover", help="封面图路径（可选）")
    args = parser.parse_args()
    
    env = load_env()
    appid = env.get("WECHAT_APPID", "")
    appsecret = env.get("WECHAT_APPSECRET", "")
    
    if not appid or not appsecret:
        print("[!] 微信凭证未配置")
        print(f"    请设置环境变量: WECHAT_APPID, WECHAT_APPSECRET")
        print(f"    或在 .env 文件: {ENV_FILE}")
        return
    
    # 1. 构建文章
    print(f"[*] 读取: {args.source}")
    article_data = build_wx_article(args.source)
    print(f"[*] 标题: {article_data['title']}")
    print(f"[*] 正文长度: {article_data['body_length']} bytes")
    
    # 2. 上传封面
    if args.cover:
        api = WeChatAPI(appid, appsecret)
        result = api.upload_image(args.cover)
        if "media_id" in result:
            article_data["articles"][0]["thumb_media_id"] = result["media_id"]
            # 缓存封面 media_id
            (WORKSPACE / "trading" / "cover_uploaded.txt").write_text(result["media_id"])
            print(f"[✓] 封面已更新")
    
    # 3. 发布
    api = WeChatAPI(appid, appsecret)
    if args.mode == "draft":
        result = api.add_draft(article_data["articles"])
    elif args.mode == "publish":
        draft_result = api.add_draft(article_data["articles"])
        if draft_result.get("media_id"):
            # freepublish 提交（需要对应权限）
            token = api.get_token()
            publish_payload = {"media_id": draft_result["media_id"]}
            body = json.dumps(publish_payload, ensure_ascii=False)
            url = f"{api.base_url}/freepublish/submit?access_token={token}"
            r = subprocess.run(
                ["curl", "-s", "-X", "POST", url, "-H", "Content-Type: application/json", "-d", body],
                capture_output=True, text=True, timeout=30
            )
            result = json.loads(r.stdout)
            print(f"[*] 发布结果: {json.dumps(result, ensure_ascii=False)}")
    
    print(f"[✓] 完成！请登录 mp.weixin.qq.com 查看草稿")


if __name__ == "__main__":
    main()
