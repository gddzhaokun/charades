#!/usr/bin/env python3
"""Local verification of the rebuilt CDN edition (pre-push).

Serves the repo root over http://localhost and asserts, per viewport:
  - all 50 <img> loaded: naturalWidth > 0 && complete
  - no horizontal overflow
  - key elements inside slide, word>=40px, illus>=80px
  - question text renders correctly (spot-check n=1,9,25,41,50)
  - illustration area has no pure-white pixels (multiply intact)
Usage: verify_local.py <out_json>
"""
import json, os, sys, time, threading
from http.server import HTTPServer, SimpleHTTPRequestHandler
from playwright.sync_api import sync_playwright

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
import time as _t
URL = f'http://127.0.0.1:8077/index.html?v={int(_t.time())}'

VIEWPORTS = [(390,844,'p390x844'), (360,640,'p360x640'), (844,390,'l844x390')]
SLIDE_IDX = [0, 1, 9, 31, 50]   # cover, q1 猴子, q9 蛇, q31 踢足球, q50 VR
EXPECT_WORDS = {1:'猴子', 9:'蛇', 31:'踢足球', 41:'画蛇添足', 50:'戴VR眼镜'}

JS_PROBE = r"""
(idx) => {
  const slides = document.querySelectorAll('.slide');
  const s = slides[idx];
  const sr = s.getBoundingClientRect();
  const box = (sel) => { const el = s.querySelector(sel);
    if (!el) return null;
    const r = el.getBoundingClientRect();
    return {top:+r.top.toFixed(1), bottom:+r.bottom.toFixed(1),
            left:+r.left.toFixed(1), right:+r.right.toFixed(1),
            w:+r.width.toFixed(1), h:+r.height.toFixed(1)}; };
  const word = s.querySelector('.word');
  const illus = s.querySelector('.illus');
  return {
    slide:{top:+sr.top.toFixed(1),bottom:+sr.bottom.toFixed(1),
           left:+sr.left.toFixed(1),right:+sr.right.toFixed(1)},
    illus: box('.illus'), word: box('.word'),
    hintRow: box('.hint-row'), foot: box('.foot'),
    wordFontPx: word ? parseFloat(getComputedStyle(word).fontSize) : null,
    illusW: illus ? +illus.getBoundingClientRect().width.toFixed(1) : null,
    illusH: illus ? +illus.getBoundingClientRect().height.toFixed(1) : null,
  };
}
"""

JS_IMGS = r"""
() => {
  const imgs = [...document.querySelectorAll('.illus img')];
  return { total: imgs.length,
    broken: imgs.filter(i => !i.complete || i.naturalWidth === 0).length,
    rawRefs: imgs.filter(i => /raw\.githubusercontent/.test(i.src)).length,
    sameOrigin: imgs.filter(i => i.src.includes(window.location.origin) ||
                               (!i.src.startsWith('http'))).length };
}
"""

JS_TEXT = r"""
(qn) => {
  const slides = document.querySelectorAll('.slide');
  for (const s of slides) {
    const c = s.querySelector('.counter');
    if (c && c.textContent.includes(String(qn))) {
      return s.querySelector('.word').textContent.trim();
    }
  }
  return null;
}
"""

JS_PIXELS = r"""
"""
def pixel_check(page, idx):
    """Screenshot the .illus element, count pure-white pixels."""
    slides = page.evaluate("() => document.querySelectorAll('.slide').length")
    _ = slides
    el = page.evaluate_handle(
        f"() => document.querySelectorAll('.slide')[{idx}].querySelector('.illus')")
    img = el.as_element()
    if not img:
        return None
    buf = img.screenshot()
    import io
    from PIL import Image
    im = Image.open(io.BytesIO(buf)).convert('RGB')
    px = im.load()
    w, h = im.size
    white = sum(1 for y in range(h) for x in range(w)
                if px[x,y] == (255,255,255))
    return {'size': [w,h], 'pureWhitePct': round(100*white/(w*h), 2)}


def main():
    out = sys.argv[1] if len(sys.argv) > 1 else 'v5-local-verify.json'
    os.chdir(ROOT)
    handler = SimpleHTTPRequestHandler
    httpd = HTTPServer(('127.0.0.1', 8077), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()

    report = {'when': time.strftime('%F %T'), 'url': URL, 'viewports': []}
    fails = []
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(args=['--no-sandbox'])
            for (w,h,name) in VIEWPORTS:
                ctx = browser.new_context(viewport={'width':w,'height':h},
                                          device_scale_factor=2)
                page = ctx.new_page()
                page.goto(URL, wait_until='domcontentloaded', timeout=30000)
                page.wait_for_timeout(1500)
                # images settle
                for _ in range(30):
                    n = page.evaluate(
                        "() => [...document.querySelectorAll('.illus img')]"
                        ".filter(i=>i.complete).length")
                    if n >= 50: break
                    page.wait_for_timeout(300)
                imgs = page.evaluate(JS_IMGS)
                docw = page.evaluate(
                    "() => [document.documentElement.scrollWidth,"
                    "window.innerWidth]")
                vp = {'name':name,'w':w,'h':h,'imgs':imgs,
                      'scrollCheck':docw,'slides':[]}
                if imgs['broken'] or imgs['total'] != 50:
                    fails.append(f'{name}: imgs {imgs}')
                if docw[0] != docw[1]:
                    fails.append(f'{name}: h-overflow {docw}')
                for idx in SLIDE_IDX:
                    pr = page.evaluate(JS_PROBE, idx)
                    if pr:
                        pr['n'] = idx
                        vp['slides'].append(pr)
                        s = pr['slide']; sl = pr['slide']
                        for k in ('illus','word','hintRow','foot'):
                            b = pr[k]
                            if b and (b['left'] < sl['left']-1 or
                                      b['right'] > sl['right']+1 or
                                      b['top'] < sl['top']-1 or
                                      b['bottom'] > sl['bottom']+1):
                                fails.append(f'{name} slide{idx} {k} overflow {b}')
                        if pr['wordFontPx'] and pr['wordFontPx'] < 40:
                            fails.append(f'{name} slide{idx} font {pr["wordFontPx"]}')
                        if pr['illusW'] and pr['illusW'] < 80:
                            fails.append(f'{name} slide{idx} illus {pr["illusW"]}')
                # text spot checks
                texts = {}
                for qn, expect in EXPECT_WORDS.items():
                    got = page.evaluate(JS_TEXT, qn)
                    texts[str(qn)] = got
                    if got != expect:
                        fails.append(f'{name} q{qn} text got {got!r} expect {expect!r}')
                vp['textSpot'] = texts
                # pixel check on 2 representative slides
                vp['pixels'] = {}
                for idx in (1, 31):
                    r = pixel_check(page, idx)
                    vp['pixels'][str(idx)] = r
                    if r and r['pureWhitePct'] > 0.5:
                        fails.append(f'{name} slide{idx} white {r["pureWhitePct"]}%')
                page.screenshot(path=f'/tmp/charades-v5/shot-{name}.png')
                report['viewports'].append(vp)
                print(f'{name}: imgs={imgs["total"]}/{imgs["broken"]} '
                      f'texts={texts} ok' if not fails else f'{name}: done')
                ctx.close()
    finally:
        httpd.shutdown()
    report['fails'] = fails
    json.dump(report, open(out,'w'), ensure_ascii=False, indent=1)
    print('FAILS:', len(fails))
    for f in fails[:10]: print(' -', f)
    return 1 if fails else 0

if __name__ == '__main__':
    sys.exit(main())
