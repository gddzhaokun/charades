#!/usr/bin/env python3
"""Real-network verification of the CDN edition of the charades game.

Opens the LIVE GitHub raw HTML (real network, real CDN) in headless Chromium
and asserts, per viewport:
  - all 50 <img> loaded: naturalWidth > 0 && complete === true  (0 broken)
  - no horizontal overflow: documentElement.scrollWidth == innerWidth
  - key elements (.illus/.word/.hint-row/.foot) inside their slide box
  - .word font-size >= 40px, .illus box >= 80px
Also records resource timing for the CDN images.

Usage: verify_cdn.py [out_json]
"""
import json, os, sys, time
from playwright.sync_api import sync_playwright

URL = ('https://gddzhaokun.github.io/charades/')
# NOTE: GitHub raw serves .html as text/plain, so browsers refuse to render
# it (Playwright showed a blank page).  GitHub Pages serves the SAME file as
# text/html, so Pages hosts the HTML while raw hosts the 50 WebP images.

VIEWPORTS = [
    (390, 844, 'portrait-390x844'),
    (360, 640, 'portrait-360x640'),
    (844, 390, 'landscape-844x390'),
    (430, 932, 'portrait-430x932'),
]

SLIDE_IDX = [0, 1, 6, 36, 50]
# slides[0] = cover, slides[k] = question k (1-based) -> the DoD asks for
# q1 / q6 / q36 / q50, i.e. slide indices 1 / 6 / 36 / 50 (NOT 0/5/35/49).

JS_PROBE = r"""
(idx) => {
  const slides = document.querySelectorAll('.slide');
  const s = slides[idx];
  const sr = s.getBoundingClientRect();
  const box = (sel) => {
    const el = s.querySelector(sel);
    if (!el) return null;
    const r = el.getBoundingClientRect();
    return {top:+r.top.toFixed(1), bottom:+r.bottom.toFixed(1),
            left:+r.left.toFixed(1), right:+r.right.toFixed(1),
            w:+r.width.toFixed(1), h:+r.height.toFixed(1)};
  };
  const word = s.querySelector('.word');
  const illus = s.querySelector('.illus');
  return {
    slide: {top:+sr.top.toFixed(1), bottom:+sr.bottom.toFixed(1),
            left:+sr.left.toFixed(1), right:+sr.right.toFixed(1),
            w:+sr.width.toFixed(1), h:+sr.height.toFixed(1)},
    illus: box('.illus'),
    word: box('.word'),
    hintRow: box('.hint-row'),
    foot: box('.foot'),
    wordFontPx: word ? parseFloat(getComputedStyle(word).fontSize) : null,
    illusW: illus ? illus.getBoundingClientRect().width : null,
    illusH: illus ? illus.getBoundingClientRect().height : null,
  };
}
"""

JS_IMGS = r"""
() => {
  const imgs = [...document.querySelectorAll('.illus img')];
  return {
    total: imgs.length,
    broken: imgs.filter(i => !i.complete || i.naturalWidth === 0).length,
    details: imgs.map((i, k) => ({
      idx: k, src: i.currentSrc || i.src,
      natW: i.naturalWidth, natH: i.naturalHeight,
      complete: i.complete,
    })),
  };
}
"""

JS_TIMING = r"""
() => {
  const rs = performance.getEntriesByType('resource')
    .filter(r => /assets\/img\/.*\.webp/.test(r.name));
  const dur = rs.map(r => r.duration);
  const sizes = rs.map(r => r.transferSize || 0);
  return {
    imgRequests: rs.length,
    totalTransferBytes: sizes.reduce((a, b) => a + b, 0),
    avgMs: dur.length ? +(dur.reduce((a, b) => a + b, 0) / dur.length).toFixed(1) : null,
    maxMs: dur.length ? +Math.max(...dur).toFixed(1) : null,
    minMs: dur.length ? +Math.min(...dur).toFixed(1) : null,
    nav: (() => { const n = performance.getEntriesByType('navigation')[0];
      return n ? {domContentLoaded: +n.domContentLoadedEventEnd.toFixed(1),
                  load: +n.loadEventEnd.toFixed(1),
                  responseEnd: +n.responseEnd.toFixed(1)} : null; })(),
  };
}
"""


def main():
    out_path = sys.argv[1] if len(sys.argv) > 1 else 'cdn-verify-report.json'
    report = {'url': URL, 'when': time.strftime('%Y-%m-%d %H:%M:%S'),
              'viewports': []}
    fails = []

    with sync_playwright() as p:
        browser = p.chromium.launch(args=['--no-sandbox'])
        for (w, h, name) in VIEWPORTS:
            ctx = browser.new_context(viewport={'width': w, 'height': h},
                                      device_scale_factor=2)
            page = ctx.new_page()
            vp = {'name': name, 'w': w, 'h': h, 'slides': [], 'checks': []}

            t0 = time.time()
            # NOTE: wait_until='load' is flaky here — GitHub raw throttles the
            # 50 parallel image requests, so the load event can exceed 60s.
            # Navigate on domcontentloaded, then wait for the images.
            # GitHub Pages also intermittently stalls; retry the navigation.
            resp, last_err = None, None
            for attempt in range(3):
                try:
                    resp = page.goto(URL, wait_until='domcontentloaded',
                                     timeout=45000)
                    break
                except Exception as e:
                    last_err = e
                    print(f'  [retry {attempt + 1}] goto failed: '
                          f'{type(e).__name__}', flush=True)
                    page.wait_for_timeout(4000)
            if resp is None:
                fails.append(f'{name}: navigation failed after 3 tries '
                             f'({type(last_err).__name__})')
                report['viewports'].append(vp)
                ctx.close()
                continue
            vp['httpStatus'] = resp.status if resp else None
            vp['navWallMs'] = round((time.time() - t0) * 1000, 1)

            # wait for every image to settle (decode or error)
            page.wait_for_function(
                "() => { const i=[...document.querySelectorAll('.illus img')];"
                " return i.length===50 && i.every(x=>x.complete); }",
                timeout=120000)
            page.wait_for_timeout(600)

            # --- images ---
            imgs = page.evaluate(JS_IMGS)
            vp['imgTotal'] = imgs['total']
            vp['imgBroken'] = imgs['broken']
            vp['imgSample'] = imgs['details'][:2] + imgs['details'][-2:]
            if imgs['total'] != 50:
                fails.append(f'{name}: img total {imgs["total"]} != 50')
            if imgs['broken'] != 0:
                fails.append(f'{name}: {imgs["broken"]} broken images')
            if any(d['natW'] != 384 for d in imgs['details']):
                bad = [d for d in imgs['details'] if d['natW'] != 384]
                fails.append(f'{name}: {len(bad)} images not 384px wide')

            # --- timing ---
            vp['timing'] = page.evaluate(JS_TIMING)

            # --- horizontal overflow ---
            sw = page.evaluate('document.documentElement.scrollWidth')
            iw = page.evaluate('window.innerWidth')
            vp['scrollWidth'] = sw
            vp['innerWidth'] = iw
            if sw != iw:
                fails.append(f'{name}: horizontal overflow {sw} != {iw}')

            # --- per-slide geometry ---
            for si in SLIDE_IDX:
                g = page.evaluate(JS_PROBE, si)
                rec = {'slideIdx': si,
                       'label': 'cover' if si == 0 else f'q{si}',
                       **g}
                sb, sl = g['slide'], g['slide']
                issues = []
                for key in ('illus', 'word', 'hintRow', 'foot'):
                    b = g[key]
                    if b is None:
                        continue
                    if b['left'] < sl['left'] - 1 or b['right'] > sl['right'] + 1:
                        issues.append(f'{key} x-overflow')
                    if b['top'] < sl['top'] - 1 or b['bottom'] > sl['bottom'] + 1:
                        issues.append(f'{key} y-overflow')
                if g['wordFontPx'] is not None and g['wordFontPx'] < 40:
                    issues.append(f'word font {g["wordFontPx"]}px < 40')
                if g['illusW'] is not None and g['illusW'] < 80:
                    issues.append(f'illus width {g["illusW"]}px < 80')
                rec['issues'] = issues
                vp['slides'].append(rec)
                for it in issues:
                    fails.append(f'{name} slide#{si}: {it}')

            page.screenshot(path=f'cdn-shots/{name}.png', full_page=False)
            ctx.close()
            report['viewports'].append(vp)
            print(f'[OK] {name}  status={vp["httpStatus"]}  '
                  f'img={vp["imgTotal"]} broken={vp["imgBroken"]}  '
                  f'sw={sw}/{iw}  '
                  f'avgImgMs={vp["timing"]["avgMs"]}  '
                  f'transferKB={vp["timing"]["totalTransferBytes"]//1024}',
                  flush=True)

        browser.close()
    report['fails'] = fails
    report['pass'] = len(fails) == 0
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=1)
    print(f'\n=== {"PASS" if report["pass"] else "FAIL"} : {len(fails)} issue(s) ===')
    for x in fails:
        print('  !', x)
    return 0 if report['pass'] else 1


if __name__ == '__main__':
    sys.exit(main())
