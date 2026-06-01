#!/usr/bin/env python3
"""
wechat_publisher.py - 公众号文章发布工具
功能：
  1. 读取博客生成的 HTML 文章
  2. 转换为公众号兼容格式
  3. 上传图片到公众号素材库
  4. 发布到草稿箱或直接发布

用法：
  python3 wechat_publisher.py --mode draft    # 推送到草稿箱
  python3 wechat_publisher.py --mode publish # 直接发布（服务号）
  python3 wechat_publisher.py --source blog/closes/2026-05-25.html

依赖：
  pip install requests Pillow

公众号凭证（从环境变量或 config 文件读取）
  WECHAT_APPID / WECHAT_APPSECRET
"""

import os
import re
import json
import base64
import time
import mimetypes
import subprocess
from pathlib import Path
from datetime import datetime

# ─── 凭证配置 ───────────────────────────────────────────────────────────────
APPID     = os.environ.get("WECHAT_APPID", "")
APPSECRET = os.environ.get("WECHAT_APPSECRET", "")
ACCESS_TOKEN = ""

WORKSPACE = Path(__file__).resolve().parent.parent

# ─── 免责模板（每次发布强制插入）────────────────────────────────────────────
DISCLAIMER = """
<div style="background:#fff3e0;border-left:4px solid #ff9800;padding:12px 16px;margin:16px 0;border-radius:4px">
<strong>⚠️ 风险提示</strong><br/>
本公众号所有内容仅作为个人交易系统的研究与记录，不构成任何投资建议。
投资者据此操作，风险自担。A股市场有风险，入市需谨慎。
</div>
"""

# ─── 微信公众号 API ─────────────────────────────────────────────────────────
class WeChatAPI:
    """公众号 API 封装"""

    def __init__(self, appid, appsecret):
        self.appid = appid
        self.appsecret = appsecret
        self.base_url = "https://api.weixin.qq.com/cgi-bin"
        self._token = None
        self._token_expires = 0

    def _load_token(self):
        """尝试从本地缓存读取 token"""
        token_file = WORKSPACE / ".wechat_token.json"
        if token_file.exists():
            try:
                data = json.loads(token_file.read_text())
                if data.get("expires_at", 0) > time.time() + 60:
                    self._token = data["access_token"]
                    self._token_expires = data["expires_at"]
                    return
            except Exception:
                pass

    def _save_token(self):
        """保存 token 到本地"""
        token_file = WORKSPACE / ".wechat_token.json"
        token_file.write_text(json.dumps({
            "access_token": self._token,
            "expires_at": self._token_expires
        }, ensure_ascii=False))

    def get_token(self, force_refresh=False) -> str:
        """获取 access_token（自动缓存）"""
        if not force_refresh and self._token and time.time() < self._token_expires - 60:
            return self._token

        url = f"{self.base_url}/token?grant_type=client_credential&appid={self.appid}&secret={self.appsecret}"
        r = subprocess.run(
            ["curl", "-s", url],
            capture_output=True, text=True, timeout=15
        )
        result = json.loads(r.stdout)
        if "access_token" in result:
            self._token = result["access_token"]
            self._token_expires = time.time() + result.get("expires_in", 7200)
            self._save_token()
            print(f"[✓] Token 刷新成功: {self._token[:20]}...")
            return self._token
        else:
            raise Exception(f"获取 Token 失败: {result}")

    def api(self, path: str, method="GET", data=None, token=None) -> dict:
        """通用 API 请求"""
        if token is None:
            token = self.get_token()
        url = f"{self.base_url}{path}?access_token={token}"
        cmd = ["curl", "-s", "-X", method.upper(), url]
        if data:
            if isinstance(data, str):
                cmd += ["-d", data]
            else:
                cmd += ["-d", json.dumps(data, ensure_ascii=False)]
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        return json.loads(r.stdout)

    def upload_image(self, image_path: str) -> str:
        """上传永久图片素材，返回 media_id"""
        token = self.get_token()
        url = f"{self.base_url}/material/add_material?access_token={token}&type=image"
        filename = os.path.basename(image_path)
        mime = mimetypes.guess_type(filename)[0] or "image/png"

        # 用 curl 上传 multipart
        cmd = [
            "curl", "-s", "-F", f"media=@{image_path}",
            "-F", f"type={mime}",
            url
        ]
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        result = json.loads(r.stdout)
        if "media_id" in result:
            print(f"[✓] 图片上传成功: {filename} -> {result['media_id']}")
            return result["media_id"]
        else:
            print(f"[✗] 图片上传失败: {result}")
            return ""

    def add_draft(self, articles: list) -> dict:
        """添加到草稿箱（订阅号/服务号均可用）"""
        token = self.get_token()
        payload = {"articles": articles}
        result = self.api("/draft/add", method="POST", data=payload, token=token)
        if result.get("errcode") == 0:
            print(f"[✓] 草稿添加成功，media_id: {result.get('media_id')}")
        else:
            print(f"[✗] 草稿添加失败: {result}")
        return result

    def freepublish_submit(self, media_id: str) -> dict:
        """发布已发表（仅服务号，订阅号自动发布）"""
        token = self.get_token()
        payload = {"media_id": media_id}
        result = self.api("/freepublish/submit", method="POST", data=payload, token=token)
        if result.get("errcode") == 0:
            print(f"[✓] 发布任务提交成功，publish_id: {result.get('publish_id')}")
        else:
            print(f"[✗] 发布失败: {result}")
        return result


# ─── HTML 转公众号格式 ───────────────────────────────────────────────────────
def html_to_wechat(html_content: str) -> str:
    """
    将博客 HTML 转换为公众号兼容 HTML
    主要处理：
    - 图片：替换 src 为 media_id（需先上传）
    - 样式：简化内联样式（公众号对 CSS 有严格限制）
    - 安全：移除危险标签（script, iframe 等）
    """

    # 移除危险标签
    html_content = re.sub(r'<script[^>]*>.*?</script>', '', html_content, flags=re.DOTALL | re.I)
    html_content = re.sub(r'<iframe[^>]*>.*?</iframe>', '', html_content, flags=re.DOTALL | re.I)
    html_content = re.sub(r'<style[^>]*>.*?</style>', '', html_content, flags=re.DOTALL | re.I)

    # 图片处理：标记需要上传的图片路径
    def replace_img(match):
        src = match.group(1)
        # 外部图片保留 URL
        if src.startswith('http'):
            return f'<p><img src="{src}" style="width:100%;max-width:640px;border-radius:8px;margin:12px 0"/></p>'
        # 本地图片标记占位
        return f'<p><img data-local="{src}" style="width:100%;max-width:640px;border-radius:8px;margin:12px 0"/></p>'

    html_content = re.sub(r'<img[^>]+src=["\']([^"\']+)["\'][^>]*>', replace_img, html_content, flags=re.I)

    return html_content


def extract_title_and_body(html_content: str) -> tuple:
    """从 HTML 中提取标题和正文"""
    title_m = re.search(r'<h1[^>]*>(.*?)</h1>', html_content, re.DOTALL | re.I)
    title = title_m.group(1).strip() if title_m else "龙虾选股日报"

    # 移除已有的免责声明（如果有的话，防止重复）
    body = re.sub(r'<div style="background:#fff3e0[^"]*风险提示.*?</div>', '', html_content, flags=re.DOTALL | re.I)

    return title, body


def build_article_payload(title: str, content: str, author: str = "龙虾系统",
                          digest: str = "", thumb_media_id: str = "") -> dict:
    """构建公众号文章 payload"""
    if not digest:
        # 自动生成摘要（取前54字）
        clean = re.sub(r'<[^>]+>', '', content)
        clean = clean.replace('\n', ' ').strip()
        digest = clean[:54] + "..." if len(clean) > 54 else clean

    return {
        "title": title,
        "author": author,
        "digest": digest,
        "content": content,
        "content_source_url": "",
        "thumb_media_id": thumb_media_id,
        "need_open_comment": 1,
        "only_fans_can_comment": 0
    }


# ─── 主流程 ─────────────────────────────────────────────────────────────────
def publish_article(source_html: str, mode: str = "draft",
                    appid: str = "", appsecret: str = "") -> dict:
    """
    主发布函数
    mode: "draft" → 推草稿箱
          "publish" → 直接发布（服务号）
    """
    if not appid or not appsecret:
        print("[!] AppID 或 AppSecret 未设置，退出")
        return {"errcode": -1, "errmsg": "缺少凭证"}

    api = WeChatAPI(appid, appsecret)

    # 1. 解析 HTML
    title, body = extract_title_and_body(source_html)

    # 2. 插入免责
    wechat_content = body + DISCLAIMER

    # 3. HTML 格式转换
    wechat_content = html_to_wechat(wechat_content)

    # 4. 构建文章 payload
    article = build_article_payload(
        title=title,
        content=wechat_content,
        digest=f"龙虾选股系统 {datetime.now().strftime('%Y-%m-%d')} 每日报告"
    )

    # 5. 发布
    if mode == "draft":
        return api.add_draft(articles=[article])
    elif mode == "publish":
        result = api.add_draft(articles=[article])
        if result.get("media_id"):
            return api.freepublish_submit(result["media_id"])
        return result
    else:
        return {"errcode": -1, "errmsg": f"未知模式: {mode}"}


# ─── CLI 入口 ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="龙虾选股公众号发布工具")
    parser.add_argument("--mode", choices=["draft", "publish"], default="draft",
                        help="draft=推草稿箱, publish=直接发布")
    parser.add_argument("--source", default="",
                        help="源 HTML 文件路径，默认用最新收盘文章")
    parser.add_argument("--appid", default=APPID, help="微信公众号 AppID")
    parser.add_argument("--appsecret", default=APPSECRET, help="微信公众号 AppSecret")

    args = parser.parse_args()

    # 默认取当天收盘文章
    today = datetime.now().strftime("%Y-%m-%d")
    if not args.source:
        candidates = list((WORKSPACE / "blog" / "closes").glob(f"{today}*.html"))
        if candidates:
            args.source = str(candidates[0])
        else:
            print(f"[!] 找不到 {today} 的收盘文章，请用 --source 指定文件")
            exit(1)

    print(f"[*] 读取文章: {args.source}")
    html = Path(args.source).read_text(encoding="utf-8")

    print(f"[*] 发布模式: {args.mode}")
    result = publish_article(
        source_html=html,
        mode=args.mode,
        appid=args.appid,
        appsecret=args.appsecret
    )
    print(f"[*] 结果: {json.dumps(result, ensure_ascii=False)}")
