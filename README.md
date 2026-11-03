# CyrilPeng.github.io

个人主页源码。纯静态，无框架、无构建步骤、无外部字体依赖。

访问：https://cyrilpeng.github.io/ （英文版 `/en.html`）

## 结构

```
index.html            中文首页
en.html               英文首页
404.html              自定义 404
styles.css            样式，跟随系统深浅色，支持手动切换
app.js                主题切换 + 星标数拉取（localStorage 缓存 1 小时）
assets/
  icons/              线条图标（与 GitHub 主页 README 共用同一套）
  og.png              1200×630 社交分享卡
  stars.svg           VeneraNext 星标增长曲线（脚本生成）
scripts/gen-stars.py  抓取星标时间序列并重绘曲线
.github/workflows/    每周自动更新曲线
```

## 本地改动

直接编辑 HTML / CSS 即可，没有编译环节。提交到 `main` 后 Pages 约 30–60 秒重建。

```bash
git add -A && git commit -m "..." && git push
```

## 星标曲线

`assets/stars.svg` 由 `scripts/gen-stars.py` 生成，**不要手改**。

数据在 `data/stars.json`，格式是 `[["2026-06-09", 1], ...]` 的日期→累计数。曲线就是这条序列画出来的。

两个模式：

```bash
python scripts/gen-stars.py                 # 追加今天的星标快照（CI 用这个）
GH_TOKEN=$(gh auth token) python scripts/gen-stars.py   # 额外全量回填，历史更精确
```

### 为什么要自己存历史

`/repos/{owner}/{repo}/stargazers` 现在**强制要求认证**，而 Actions 自带的 `GITHUB_TOKEN` 只能访问当前仓库，读不了 `venera-next`。所以 CI 里只调公开的 `/repos/{owner}/{repo}` 拿当前总数，一天一个点地累积。

历史起点（148 天）是用带 token 的本地回填灌进去的。如果以后想提高历史精度，本地带 token 跑一次即可。

`.github/workflows/stars.yml` 每周一 10:00（北京时间）自动运行，有变化才提交；也可以到 Actions 页面手动触发。想改成每天，把 cron 改成 `0 2 * * *`。
