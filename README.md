# 你来比划我来猜 · 50 题

一个纯 CSS 翻页的「你来比划我来猜」HTML 游戏页，50 道题，每题一屏，配 50 张 AI 生成的插图。

## 直接玩

**方式一 · GitHub Pages**（固定 URL）
```
https://gddzhaokun.github.io/charades/
```

**方式二 · 本地打开**（下载 `index.html` 后用浏览器打开，插图走相对路径）
```
https://gddzhaokun.github.io/charades/index.html
```

> ⚠️ 插图**不使用** `raw.githubusercontent.com` 外链 —— 该域名在部分国内移动网络不可达，会导致全部裂图。
> 插图改为 **Pages 同域相对路径** `assets/img/NN.webp`，与 HTML 同源，手机端可正常加载。

下载后用浏览器打开即可，手机端上下滑动翻页。

## 结构

| 路径 | 说明 |
|------|------|
| `charades-cdn.html` | 游戏页（33.8 KB），插图走 Pages 同域相对路径 `assets/img/NN.webp` |
| `assets/img/NN.webp` | 50 张插图，384×384 白底 WebP，共 521 KB |
| `assets/img/manifest.json` | 逐题索引：word / cat / file / bytes / fallback |
| `src/build.py` | HTML 生成器（`--mode=inline\|cdn`） |
| `src/convert_files.py` | 原图 → 裁白边 → 方形化 → 384px WebP |
| `src/questions.json` | 50 题数据（分类 / 题目 / 3 个提示 pill） |
| `src/prompts.json` | 50 张图的 mmx 生图 prompt |

## 设计要点

- **纯 CSS 翻页**：`scroll-snap-type: y mandatory`，零 JavaScript、零 `<script>`
- **白底融合**：插图存为不透明白底 WebP，靠 `mix-blend-mode: multiply` 让纯白解析成卡片底色，视觉上白框不可见（像素级验证：插图框内纯白占比 0.00%）。相比 alpha 通道 WebP 体积小 4~5 倍
- **移动端适配**：
  - `height:100vh` + `height:100dvh` 双写（`100vh` 在移动浏览器地址栏伸缩时不可靠）
  - 矮屏分支按 **高度** 判定（`@media (max-height:520px)`），而不是宽度 —— 横屏手机（如 844×390）不该命中桌面样式
  - 所有长度走 `min(vh, vw, px)` 三向收敛，永远不会超出短边
  - 四向 `env(safe-area-inset-*)` 安全区（横屏刘海会内缩左右）
- **可访问性**：底部文字对比度 ≥ 5.39:1（AA 级）
- **无障碍兜底**：单张图生成失败时自动退化为 emoji，manifest 标记 `fallback: true`，不伪造成功

## 重新生成

```bash
# 1. 原图 → WebP 文件（需要 imgs/raw/NN.png）
python3 src/convert_files.py .

# 2. 生成 HTML
python3 src/build.py --mode=cdn
python3 src/build.py --mode=inline   # 单文件自包含版，约 730 KB
```

## 分类分布

动物 12 · 食物 10 · 运动 8 · 职业 8 · 物品 8 · 动作 4
