#!/usr/bin/env python3
"""charades v4 builder — light theme, one slide per question, WebP illustrations.

Reads:
  questions.json  — 50 items {n, cat, word, badge, pills, emoji}  (recovered from #4326)
  b64.json        — {n: base64_string}  WebP 512px, alpha-trimmed (optional)

Modes:
  --mode=inline  (default) — images inlined as base64 data URIs
                         -> charades-v4.html   (self-contained, ~730 KB)
  --mode=cdn               — images referenced by raw.githubusercontent.com URL
                         -> charades-cdn.html  (~35 KB, needs network)

Usage:
  python3 build.py                        # inline (default, unchanged behaviour)
  python3 build.py --mode=cdn \
      --base-url=https://raw.githubusercontent.com/gddzhaokun/charades/main
"""
import json, os, sys, html

BASE = os.path.dirname(os.path.abspath(__file__))
questions = json.load(open(os.path.join(BASE, 'questions.json')))

# ---- CLI args ----------------------------------------------------------
MODE = 'inline'
BASE_URL = 'https://raw.githubusercontent.com/gddzhaokun/charades/main'
for _a in sys.argv[1:]:
    if _a.startswith('--mode='):
        MODE = _a.split('=', 1)[1]
    elif _a.startswith('--base-url='):
        BASE_URL = _a.split('=', 1)[1].rstrip('/')
    elif _a in ('--help', '-h'):
        print(__doc__)
        sys.exit(0)
if MODE not in ('inline', 'cdn'):
    print(f'unknown --mode={MODE} (expected inline|cdn)')
    sys.exit(2)

b64_path = os.path.join(BASE, 'b64.json')
b64 = json.load(open(b64_path)) if os.path.exists(b64_path) else {}
b64 = {int(k): v for k, v in b64.items()}

# CDN mode needs the manifest to know which questions really have a file
# (and which fell back to emoji).  Optional — missing manifest => all emoji.
_manifest_path = os.path.join(BASE, 'manifest.json')
if not os.path.exists(_manifest_path):
    _manifest_path = os.path.join(BASE, 'assets', 'img', 'manifest.json')
manifest = json.load(open(_manifest_path)) if os.path.exists(_manifest_path) else {}

# NOTE: the #4326 copy-paste bug (question 36 「理发师」 carrying question 34
# 「老师」's hints 粉笔/上课/教书) is fixed directly in questions.json, so the
# single source of truth is the data file, not a build-time patch.

CAT_META = {
    'animal': ('🐶', '动物', '#ff6b9d', '#fff0f5'),
    'food':   ('🍕', '食物', '#ff922b', '#fff8f0'),
    'sport':  ('⚽', '运动', '#339af0', '#f0f7ff'),
    'job':    ('👨\u200d⚕️', '职业', '#51cf66', '#f2fbf4'),
    'object': ('📱', '物品', '#845ef7', '#f6f3ff'),
    'action': ('🙌', '动作', '#f59f00', '#fffbf0'),
}
CAT_ORDER = ['animal', 'food', 'sport', 'job', 'object', 'action']

# per-category running index for the "1/12" badge
cat_counts = {}
for q in questions:
    cat_counts[q['cat']] = cat_counts.get(q['cat'], 0) + 1
cat_seen = {}


def esc(s):
    return html.escape(str(s), quote=True)


CSS = """
*{box-sizing:border-box;margin:0;padding:0;-webkit-tap-highlight-color:transparent}
html,body{height:100%;width:100%;overflow:hidden;background:#e8ecf3;
  font-family:-apple-system,BlinkMacSystemFont,"PingFang SC","Hiragino Sans GB","Microsoft YaHei",sans-serif;
  color:#1a1a2e;-webkit-font-smoothing:antialiased}

/* ---------- pure-CSS page flipping ---------- */
/* 100vh is UNRELIABLE on mobile: iOS Safari / Android Chrome resize the visual
   viewport when the address bar shows/hides, so 100vh != visible height.
   Declare 100vh first (fallback), then 100dvh (dynamic viewport) so supporting
   browsers use the *actual* visible height. .slide MUST track .scroller exactly
   or scroll-snap misaligns. */
.scroller{height:100vh;height:100dvh;width:100%;overflow-y:scroll;scroll-snap-type:y mandatory;
  -webkit-overflow-scrolling:touch;scrollbar-width:none;overscroll-behavior-y:contain}
.scroller::-webkit-scrollbar{display:none}

.slide{height:100vh;height:100dvh;width:100%;scroll-snap-align:start;scroll-snap-stop:always;
  display:flex;flex-direction:column;align-items:center;justify-content:center;
  position:relative;overflow:hidden;
  /* safe-area on ALL four edges — landscape notched phones inset left/right too */
  padding:calc(env(safe-area-inset-top,0px) + 52px)
          calc(env(safe-area-inset-right,0px) + 16px)
          calc(env(safe-area-inset-bottom,0px) + 44px)
          calc(env(safe-area-inset-left,0px) + 16px)}

/* ---------- cover ---------- */
.slide-intro{background:linear-gradient(135deg,#667eea 0%,#764ba2 100%);color:#fff}
.slide-intro .big{font-size:clamp(40px,11vw,64px);font-weight:900;letter-spacing:.02em;
  text-align:center;line-height:1.25;text-shadow:0 6px 24px rgba(0,0,0,.28)}
.slide-intro .sub{font-size:clamp(15px,4vw,20px);opacity:.95;margin-top:20px;text-align:center;line-height:1.8}
.slide-intro .chips{margin-top:26px;display:flex;flex-wrap:wrap;gap:8px;
  justify-content:center;max-width:92%}
.slide-intro .cchip{background:rgba(255,255,255,.18);border:1px solid rgba(255,255,255,.32);
  padding:7px 14px;border-radius:14px;font-size:clamp(12px,3.2vw,15px);font-weight:600;
  white-space:nowrap;backdrop-filter:blur(6px)}
.slide-intro .cchip b{font-weight:900;margin-left:2px}
.slide-intro .scroll-hint{position:absolute;bottom:calc(env(safe-area-inset-bottom,0px) + 30px);
  font-size:16px;font-weight:700;opacity:.92;letter-spacing:.5px;
  animation:bounce 1.8s ease-in-out infinite}
@keyframes bounce{0%,100%{transform:translateY(0)}50%{transform:translateY(9px)}}

/* ---------- question slide ---------- */
.slide-q{background:var(--bg,#f8f9fc);--accent:#666}
/* cat-badge + counter: same top offset AND same explicit height so their
   visual centre lines match exactly (previously 16px vs 12px top with
   different box heights -> visibly misaligned). */
.cat-badge{position:absolute;top:calc(env(safe-area-inset-top,0px) + 13px);left:0;right:0;
  height:26px;line-height:26px;padding:0 94px;overflow:hidden;
  text-align:center;font-size:15px;font-weight:800;color:var(--accent);
  letter-spacing:1.5px;white-space:nowrap}
.counter{position:absolute;top:calc(env(safe-area-inset-top,0px) + 13px);
  right:calc(env(safe-area-inset-right,0px) + 14px);
  display:inline-flex;align-items:center;height:26px;padding:0 13px;
  background:var(--accent);color:#fff;border-radius:20px;
  font-size:14px;font-weight:800;box-shadow:0 3px 10px rgba(0,0,0,.13)}

/* illustration: takes the top half of the slide.
   Images are stored as OPAQUE white-bg WebP (4-5x smaller than alpha WebP);
   mix-blend-mode:multiply makes pure white resolve to exactly the card
   background colour, so the white box is invisible (verified by pixel
   sampling a rendered screenshot: 0 pure-white pixels survive). */
.illus{width:min(46vh,52vw,250px);height:min(46vh,52vw,250px);
  width:min(46dvh,52vw,250px);height:min(46dvh,52vw,250px);
  display:flex;align-items:center;justify-content:center;margin-bottom:clamp(6px,2vh,18px)}
.illus img{width:100%;height:100%;object-fit:contain;
  mix-blend-mode:multiply;isolation:isolate}
.illus .emoji{font-size:min(30vh,38vw,170px);line-height:1}

/* the word — the single most important element on screen */
.word{font-size:min(19vw,118px);font-size:min(19vw,118px,14dvh);font-weight:900;
  line-height:1.05;color:#111;
  letter-spacing:.03em;text-align:center;word-break:keep-all;
  margin:0 0 clamp(10px,2.4vh,22px);padding:0 4px}

/* hint pills */
.hint-row{display:flex;flex-wrap:wrap;gap:8px;justify-content:center;max-width:96%}
.pill{background:#fff;border:1.5px solid rgba(26,26,46,.10);
  padding:8px 15px;border-radius:16px;font-size:clamp(13px,3.5vw,16px);
  font-weight:700;color:#333;box-shadow:0 3px 10px rgba(26,26,46,.07);white-space:nowrap}

.foot{position:absolute;bottom:calc(env(safe-area-inset-bottom,0px) + 14px);
  font-size:13px;color:#5a6478;font-weight:600;letter-spacing:.5px}

/* ---------- end slide ---------- */
.slide-end{background:linear-gradient(135deg,#11998e 0%,#38ef7d 100%);color:#fff}
.slide-end .big{font-size:clamp(60px,17vw,96px);line-height:1}
.slide-end p{font-size:clamp(16px,4.2vw,20px);opacity:.96;margin-top:18px;text-align:center;line-height:1.7}

/* ================= responsive sizing =================
   The OLD rule was `@media (min-width:600px)` — a pure WIDTH test. A phone in
   landscape (844x390, 932x430 …) is "wide" but only ~360-430px tall, so it
   wrongly matched the desktop branch and got .word=150px / .illus=300px,
   which overflows a 390px-tall slide. Size must follow the SHORTER axis.
   Strategy: portrait/normal is the base (below); SHORT screens (landscape
   phones + tiny windows) get a dedicated compact branch keyed on height.
   Landscape phones are also *height*-constrained, so every length below is
   `min(<vh term>, <vw term>, <px cap>)` — it can never exceed the short axis. */

/* base portrait tweaks: .illus may shrink if a long word + 3 wrapped pills
   would overflow; min-height:0 removes the automatic min-content floor so
   flexbox is allowed to compress it instead of pushing content out of view. */
.illus{flex:0 1 auto;min-height:0}
.word,.hint-row{flex:0 0 auto}

/* SHORT viewports — landscape phones (844x390 / 740x360 / 667x375 / 932x430)
   and short portrait windows (360x480 / 360x520). */
@media (max-height:520px){
  .slide{padding:calc(env(safe-area-inset-top,0px) + max(34px,8dvh))
                 calc(env(safe-area-inset-right,0px) + 14px)
                 calc(env(safe-area-inset-bottom,0px) + max(26px,7dvh))
                 calc(env(safe-area-inset-left,0px) + 14px)}
  .illus{width:min(30dvh,27vw,240px);height:min(30dvh,27vw,240px);
    margin-bottom:min(2dvh,10px)}
  .word{font-size:min(17vw,15dvh,90px);margin-bottom:min(2.2dvh,12px)}
  .pill{font-size:13px;padding:6px 12px;border-radius:14px}
  .hint-row{gap:6px}
  .cat-badge{top:calc(env(safe-area-inset-top,0px) + 8px);height:22px;line-height:22px;
    font-size:13px;letter-spacing:1px;padding:0 82px}
  .counter{top:calc(env(safe-area-inset-top,0px) + 8px);height:22px;font-size:12px;padding:0 11px}
  .foot{font-size:11.5px;bottom:calc(env(safe-area-inset-bottom,0px) + 8px)}
  /* cover / end must also fit a 360px-tall viewport */
  .slide-intro .big{font-size:clamp(30px,6.4dvh,46px);line-height:1.2}
  .slide-intro .sub{font-size:13px;margin-top:10px;line-height:1.6}
  .slide-intro .chips{margin-top:12px;gap:6px}
  .slide-intro .cchip{padding:5px 10px;font-size:12px}
  .slide-intro .scroll-hint{font-size:13px;bottom:calc(env(safe-area-inset-bottom,0px) + 10px)}
  .slide-end .big{font-size:clamp(44px,22dvh,72px)}
  .slide-end p{font-size:15px;margin-top:10px;line-height:1.6}
}

/* Roomy desktop / tablet windows only — BOTH axes must be comfortable.
   (min-height guard is what keeps landscape phones out of this branch.) */
@media (min-width:600px) and (min-height:521px){
  .word{font-size:min(150px,16dvh)}
  .illus{width:300px;height:300px}
}
"""


def build():
    parts = []
    parts.append('<!DOCTYPE html>\n<html lang="zh-CN">\n<head>\n'
                 '<meta charset="UTF-8">\n'
                 '<meta name="viewport" content="width=device-width, initial-scale=1.0, '
                 'maximum-scale=1.0, user-scalable=no, viewport-fit=cover">\n'
                 '<meta name="apple-mobile-web-app-capable" content="yes">\n'
                 '<meta name="theme-color" content="#e8ecf3">\n'
                 '<title>你来比划我来猜 · 50 题</title>\n<style>')
    parts.append(CSS)
    parts.append('</style>\n</head>\n<body>\n<div class="scroller">\n')

    n_img = len(b64)
    cover_cats = ' · '.join(f'{CAT_META[c][1]}{cat_counts[c]}' for c in CAT_ORDER if c in cat_counts)
    chips = ''.join(
        f'<span class="cchip">{CAT_META[c][0]} {CAT_META[c][1]} <b>{cat_counts[c]}</b></span>'
        for c in CAT_ORDER if c in cat_counts)
    parts.append(
        '  <section class="slide slide-intro">\n'
        '    <div class="big">你来比划<br>我来猜</div>\n'
        f'    <div class="sub">{len(questions)} 道题 · 一题一屏</div>\n'
        f'    <div class="chips">{chips}</div>\n'
        '    <div class="scroll-hint">👆 向上滑动开始</div>\n'
        '  </section>\n')

    total = len(questions)
    for q in questions:
        cat = q['cat']
        icon, cname, accent, bg = CAT_META.get(cat, ('❓', '其他', '#666', '#f8f9fc'))
        cat_seen[cat] = cat_seen.get(cat, 0) + 1
        badge = f'{icon} {cname} · {cat_seen[cat]}/{cat_counts[cat]}'

        if MODE == 'cdn':
            entry = manifest.get(str(q['n']), {})
            if not entry.get('fallback', True) and entry.get('file'):
                src = f'{BASE_URL}/{entry["file"]}'
                # NOTE: no loading="lazy" — inside a scroll-snap scroller the
                # off-screen slides are ~50 viewports away, so lazy images would
                # never load. Total payload is only ~521 KB, so eager is fine.
                illus = (f'<img alt="{esc(q["word"])}" src="{esc(src)}" '
                         f'decoding="async">')
            else:
                illus = f'<span class="emoji">{esc(q.get("emoji") or "❓")}</span>'
        elif q['n'] in b64:
            illus = f'<img alt="{esc(q["word"])}" src="data:image/webp;base64,{b64[q["n"]]}">'
        else:
            illus = f'<span class="emoji">{esc(q.get("emoji") or "❓")}</span>'

        pills = ''.join(f'<span class="pill">💡 {esc(p)}</span>' for p in q['pills'])

        parts.append(
            f'  <section class="slide slide-q {cat}" style="--accent:{accent};--bg:{bg}">\n'
            f'    <div class="cat-badge">{esc(badge)}</div>\n'
            f'    <div class="counter">第 {q["n"]} 题</div>\n'
            f'    <div class="illus">{illus}</div>\n'
            f'    <div class="word">{esc(q["word"])}</div>\n'
            f'    <div class="hint-row">{pills}</div>\n'
            '    <div class="foot">你比划 · 朋友猜</div>\n'
            '  </section>\n')

    parts.append(
        '  <section class="slide slide-end">\n'
        '    <div class="big">🎉</div>\n'
        f'    <p>全部 {total} 题完成！<br>换个人再来一轮 →</p>\n'
        '  </section>\n')

    parts.append('</div>\n</body>\n</html>\n')
    out = os.path.join(BASE, 'charades-cdn.html' if MODE == 'cdn' else 'charades-v4.html')
    with open(out, 'w', encoding='utf-8') as f:
        f.write(''.join(parts))
    size = os.path.getsize(out)
    print(f'mode={MODE}')
    print(f'wrote {out}  {size} bytes ({size/1024:.1f} KB)')
    if MODE == 'cdn':
        n_img = sum(1 for q in questions
                    if not manifest.get(str(q['n']), {}).get('fallback', True))
        print(f'  questions={total}  cdn_images={n_img}  emoji_fallback={total-n_img}')
        print(f'  base_url={BASE_URL}')
    else:
        print(f'  questions={total}  with_image={n_img}  emoji_fallback={total-n_img}')
    return out


if __name__ == '__main__':
    build()
