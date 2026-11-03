#!/usr/bin/env python3
"""维护 VeneraNext 的星标时间序列，重绘 assets/stars.svg，并同步页面里的计数文案。

设计说明
--------
`/repos/{owner}/{repo}/stargazers` 现在强制要求认证，而 Actions 自带的
GITHUB_TOKEN 只能访问当前仓库，读不了 venera-next。所以 CI 里只调公开的
`/repos/{owner}/{repo}`（无需认证）拿当前总数，逐日累积到 data/stars.json，
曲线由这份历史数据绘制。

本地带 token 跑时会额外做一次全量回填，让历史精度更高。

用法：
    python scripts/gen-stars.py                # 只追加今天的快照
    GH_TOKEN=xxx python scripts/gen-stars.py   # 额外全量回填
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
HISTORY = os.path.join(ROOT, "data", "stars.json")
TOKEN = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
API = "https://api.github.com"

WIDTH, HEIGHT, PAD = 480, 132, 6
MONTHS_EN = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
             "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def api_get(url, accept="application/vnd.github+json", attempts=3):
    headers = {"Accept": accept, "User-Agent": "cyrilpeng-site-generator"}
    if TOKEN:
        headers["Authorization"] = "Bearer " + TOKEN
    last = None
    for i in range(attempts):
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.load(resp), resp.headers.get("Link", "")
        except urllib.error.HTTPError as exc:
            last = exc
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


def load_history():
    if not os.path.exists(HISTORY):
        return {}
    with open(HISTORY, encoding="utf-8") as fh:
        return {dt.date.fromisoformat(d): int(v) for d, v in json.load(fh)}


def save_history(series):
    os.makedirs(os.path.dirname(HISTORY), exist_ok=True)
    payload = [[d.isoformat(), v] for d, v in series]
    with open(HISTORY, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(payload, fh, ensure_ascii=False, separators=(",", ":"))


def backfill(history):
    """带 token 时翻完 stargazers 全部分页，按真实时间点重建历史。"""
    per_day, url, calls = {}, f"{API}/repos/{REPO}/stargazers?per_page=100&page=1", 0
    while url:
        batch, link = api_get(url, accept="application/vnd.github.star+json")
        calls += 1
        for item in batch:
            ts = item.get("starred_at")
            if ts:
                per_day[ts[:10]] = per_day.get(ts[:10], 0) + 1
        nxt = re.search(r'<([^>]+)>;\s*rel="next"', link)
        url = nxt.group(1) if nxt else None

    if not per_day:
        return history, calls

    merged, total, cursor = {}, 0, dt.date.fromisoformat(min(per_day))
    end = dt.date.fromisoformat(max(per_day))
    while cursor <= end:
        total += per_day.get(cursor.isoformat(), 0)
        merged[cursor] = total
        cursor += dt.timedelta(days=1)
    return merged, calls


def append_today(history):
    """用公开接口读当前总数（无需认证），写进今天这一格。"""
    payload, _ = api_get(f"{API}/repos/{REPO}")
    total = payload["stargazers_count"]
    today = dt.date.today()
    if history.get(today) == total:
        return history, total, False
    history[today] = total
    return history, total, True


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
    start = series[0][0]
    zh = f"{start.year} 年 {start.month} 月至今 · 累计 {total:,} ★"
    en = f"{MONTHS_EN[start.month - 1]} {start.year} – now · {total:,} ★"
    targets = {
        "index.html": (zh, "VeneraNext 累计星标增长曲线，" + zh.replace(" · ", "，")),
        "en.html": (en, "VeneraNext cumulative stars, " + en),
    }
    touched = []
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
    history = load_history()
    note = "仅追加今日快照"

    if TOKEN:
        try:
            history, calls = backfill(history)
            note = f"全量回填 {calls} 次请求"
        except urllib.error.HTTPError as exc:
            note = f"回填失败（HTTP {exc.code}），仅追加今日快照"

    history, total, changed = append_today(history)
    series = sorted(history.items())
    if not series:
        print("没有历史数据，放弃。", file=sys.stderr)
        return 1

    svg_path = os.path.join(ROOT, "assets", "stars.svg")
    svg = render_svg(series, total)
    old = open(svg_path, encoding="utf-8").read() if os.path.exists(svg_path) else ""
    with open(svg_path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(svg)

    save_history(series)
    touched = sync_caption(series, series[-1][1])

    print(f"{REPO}：{total:,} 颗星 · {len(series)} 天 · {note}")
    print(f"stars.svg {'已更新' if svg != old else '无变化'}；今日快照 {'已写入' if changed else '无变化'}")
    if touched:
        print("文案已同步：" + "、".join(touched))
    return 0


if __name__ == "__main__":
    sys.exit(main())
