#!/usr/bin/env python3
"""抓取 VeneraNext 的星标时间序列，重绘 assets/stars.svg，并同步页面里的计数文案。

用法：
    GH_TOKEN=xxx python scripts/gen-stars.py     # 没有 token 也能跑，只是限额低

依赖：仅标准库。CI 里由 .github/workflows/stars.yml 每周调用。
"""

import datetime as dt
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request

REPO = "CyrilPeng/venera-next"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOKEN = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
API = "https://api.github.com"

WIDTH, HEIGHT, PAD = 480, 132, 6
MONTHS_EN = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
             "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


USE_TOKEN = bool(TOKEN)


def _request(url, with_token):
    headers = {
        "Accept": "application/vnd.github.star+json",
        "User-Agent": "cyrilpeng-site-generator",
    }
    if with_token and TOKEN:
        headers["Authorization"] = "Bearer " + TOKEN
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp), resp.headers.get("Link", "")


def fetch(url, attempts=3):
    """带退避的重试。GITHUB_TOKEN 只对当前仓库有效，
    在 CI 里读别的仓库会 403，这里自动退回匿名访问。"""
    global USE_TOKEN
    last = None
    for i in range(attempts):
        try:
            return _request(url, USE_TOKEN)
        except urllib.error.HTTPError as exc:
            last = exc
            if exc.code == 403 and USE_TOKEN:
                USE_TOKEN = False          # 安装令牌读不了别的仓库，改用匿名
                continue
            if exc.code in (403, 429, 500, 502, 503, 504) and i < attempts - 1:
                time.sleep(2 ** (i + 1))
                continue
            raise
        except urllib.error.URLError as exc:
            last = exc
            if i < attempts - 1:
                time.sleep(2 ** (i + 1))
                continue
            raise
    raise last


def collect_daily_counts():
    """翻完所有分页，返回 {date: 当天新增星标数} 和请求次数。"""
    per_day = {}
    url = f"{API}/repos/{REPO}/stargazers?per_page=100&page=1"
    calls = 0
    while url:
        batch, link = fetch(url)
        calls += 1
        for item in batch:
            ts = item.get("starred_at")
            if ts:
                day = ts[:10]
                per_day[day] = per_day.get(day, 0) + 1
        nxt = re.search(r'<([^>]+)>;\s*rel="next"', link)
        url = nxt.group(1) if nxt else None
    return per_day, calls


def build_series(per_day):
    """把稀疏的按天数据补齐成连续日累计序列。"""
    days = sorted(per_day)
    if not days:
        return [], 0
    start = dt.date.fromisoformat(days[0])
    end = dt.date.fromisoformat(days[-1])
    series, total, cursor = [], 0, start
    while cursor <= end:
        total += per_day.get(cursor.isoformat(), 0)
        series.append((cursor, total))
        cursor += dt.timedelta(days=1)
    return series, total


def render_svg(series, total):
    span_x = (WIDTH - PAD * 2) / max(len(series) - 1, 1)
    span_y = (HEIGHT - PAD * 2) / max(total, 1)
    points = [
        (round(PAD + i * span_x, 1), round(HEIGHT - PAD - v * span_y, 1))
        for i, (_, v) in enumerate(series)
    ]
    line = "M" + " L".join(f"{x} {y}" for x, y in points)
    right = round(PAD + (len(series) - 1) * span_x, 1)
    area = f"{line} L{right} {HEIGHT - PAD} L{PAD} {HEIGHT - PAD} Z"
    last_x, last_y = points[-1]

    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{HEIGHT}" viewBox="0 0 {WIDTH} {HEIGHT}" fill="none" role="img" aria-label="累计星标增长曲线">
  <defs>
    <linearGradient id="stroke" x1="0" y1="0" x2="{WIDTH}" y2="0" gradientUnits="userSpaceOnUse">
      <stop stop-color="#8B5CF6"/><stop offset="1" stop-color="#EC4899"/>
    </linearGradient>
    <linearGradient id="fill" x1="0" y1="0" x2="0" y2="{HEIGHT}" gradientUnits="userSpaceOnUse">
      <stop stop-color="#8B5CF6" stop-opacity=".28"/>
      <stop offset="1" stop-color="#EC4899" stop-opacity="0"/>
    </linearGradient>
  </defs>
  <path d="{area}" fill="url(#fill)"/>
  <path d="{line}" stroke="url(#stroke)" stroke-width="2.4" stroke-linejoin="round" stroke-linecap="round"/>
  <circle cx="{last_x}" cy="{last_y}" r="4" fill="#EC4899"/>
</svg>
'''


def sync_caption(series, total):
    """把 HTML 里的计数文案和 alt 换成最新值，避免和页面上的实时数字打架。"""
    start = series[0][0]
    zh_caption = f"{start.year} 年 {start.month} 月至今 · 累计 {total:,} ★"
    en_caption = f"{MONTHS_EN[start.month - 1]} {start.year} – now · {total:,} ★"
    touched = []

    targets = {
        "index.html": (zh_caption, f"VeneraNext 累计星标增长曲线，{zh_caption.replace(' · ', '，')}"),
        "en.html": (en_caption, f"VeneraNext cumulative stars, {en_caption}"),
    }

    for name, (caption, alt) in targets.items():
        path = os.path.join(ROOT, name)
        if not os.path.exists(path):
            continue
        with open(path, encoding="utf-8") as fh:
            html = fh.read()
        before = html
        html = re.sub(r"<figcaption>.*?</figcaption>",
                      f"<figcaption>{caption}</figcaption>", html, count=1)
        html = re.sub(r'(<img src="assets/stars\.svg" alt=")[^"]*(")',
                      lambda m: m.group(1) + alt + m.group(2), html, count=1)
        if html != before:
            with open(path, "w", encoding="utf-8", newline="") as fh:
                fh.write(html)
            touched.append(name)

    return touched


def main():
    per_day, calls = collect_daily_counts()
    series, total = build_series(per_day)
    if total == 0:
        print("没有取到任何星标数据，放弃。", file=sys.stderr)
        return 1

    svg_path = os.path.join(ROOT, "assets", "stars.svg")
    svg = render_svg(series, total)
    old = ""
    if os.path.exists(svg_path):
        with open(svg_path, encoding="utf-8") as fh:
            old = fh.read()
    with open(svg_path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(svg)

    touched = sync_caption(series, total)
    mode = "带 token" if USE_TOKEN else "匿名"
    print(f"仓库 {REPO}：{total:,} 颗星，{len(series)} 天，{calls} 次请求（{mode}）")
    print(f"stars.svg {'已更新' if svg != old else '无变化'}")
    if touched:
        print("文案已同步：" + "、".join(touched))
    return 0


if __name__ == "__main__":
    sys.exit(main())
