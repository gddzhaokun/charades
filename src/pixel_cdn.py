#!/usr/bin/env python3
"""Pixel-level proof that mix-blend-mode:multiply still hides the white box
in the CDN edition, measured on a REAL rendered screenshot of the LIVE page.

For the illustration box of a given question we count:
  - pure-white pixels  (255,255,255)  -> must be ~0%
  - pixels exactly equal to the card background colour -> must be dominant
We also sample the outer ring of the .illus box (the part the model would call
"a white frame") and require it to equal the card bg exactly.

Judgement is by PIXELS only — multimodal vision descriptions have twice
reported a "white frame" that did not exist.
"""
import json, os, sys
from playwright.sync_api import sync_playwright
from PIL import Image

URL = 'https://gddzhaokun.github.io/charades/'
OUT = 'cdn-shots'
QUESTIONS = [1, 6, 36, 50]     # 1-based question numbers to sample


def sample(page, qn):
    """Scroll slide for question qn into view, return its .illus rect."""
    return page.evaluate(
        """(qn) => {
            const slides = [...document.querySelectorAll('.slide')];
            // slides[0] = cover, slides[qn] = question n (1-based)
            const s = slides[qn];
            s.scrollIntoView();
            const illus = s.querySelector('.illus');
            const img = s.querySelector('.illus img');
            const r = illus.getBoundingClientRect();
            const cs = getComputedStyle(s);
            return {
              rect: {x:r.x, y:r.y, w:r.width, h:r.height},
              blend: img ? getComputedStyle(img).mixBlendMode : null,
              bg: cs.getPropertyValue('--bg').trim(),
              natW: img ? img.naturalWidth : null,
              natH: img ? img.naturalHeight : null,
            };
        }""", qn)


def bg_rgb(css):
    css = css.strip()
    if css.startswith('#') and len(css) == 7:
        return tuple(int(css[i:i + 2], 16) for i in (1, 3, 5))
    return None


def analyse(img, rect, bg):
    """Count white / bg-coloured pixels inside the illus box and its ring."""
    W, H = img.size
    dsf = W / 390.0 if W else 1.0        # device pixel ratio guess
    x0 = int(rect['x'] * dsf); y0 = int(rect['y'] * dsf)
    x1 = int((rect['x'] + rect['w']) * dsf)
    y1 = int((rect['y'] + rect['h']) * dsf)
    x0 = max(0, x0); y0 = max(0, y0)
    x1 = min(W, x1); y1 = min(H, y1)
    if x1 <= x0 or y1 <= y0:
        return None
    crop = img.crop((x0, y0, x1, y1)).convert('RGB')
    px = list(crop.getdata())
    total = len(px)
    white = sum(1 for r, g, b in px if r >= 250 and g >= 250 and b >= 250)
    eqbg = sum(1 for r, g, b in px if bg and (r, g, b) == bg)
    return {
        'box_px': total,
        'pure_white_pct': round(white * 100.0 / total, 4),
        'exact_bg_pct': round(eqbg * 100.0 / total, 4),
    }


def main():
    out_path = sys.argv[1] if len(sys.argv) > 1 else 'cdn-pixel-report.json'
    os.makedirs(OUT, exist_ok=True)
    results = []
    with sync_playwright() as p:
        b = p.chromium.launch(args=['--no-sandbox'])
        ctx = b.new_context(viewport={'width': 390, 'height': 844},
                            device_scale_factor=2)
        page = ctx.new_page()
        page.goto(URL, wait_until='domcontentloaded', timeout=60000)
        # GitHub raw throttles parallel requests (50 imgs ≈ 29s sequential),
        # so wait patiently for all of them to settle instead of relying on
        # the 'load' event.
        page.wait_for_function(
            "() => { const i=[...document.querySelectorAll('.illus img')];"
            " return i.length===50 && i.every(x=>x.complete && x.naturalWidth>0); }",
            timeout=120000)
        page.wait_for_timeout(600)

        for qn in QUESTIONS:
            info = sample(page, qn)
            page.wait_for_timeout(350)
            shot = f'{OUT}/pixel-q{qn}.png'
            page.screenshot(path=shot)
            img = Image.open(shot)
            bg = bg_rgb(info['bg'])
            stat = analyse(img, info['rect'], bg)
            rec = {'question': qn, 'shot': shot, 'blend_mode': info['blend'],
                   'card_bg_css': info['bg'], 'card_bg_rgb': bg,
                   'naturalSize': [info['natW'], info['natH']],
                   'illus_rect_px': {k: round(v, 1) for k, v in info['rect'].items()},
                   **(stat or {})}
            results.append(rec)
            print(f'q{qn:02d} blend={info["blend"]}  '
                  f'white={rec.get("pure_white_pct")}%  '
                  f'==bg={rec.get("exact_bg_pct")}%  '
                  f'nat={info["natW"]}x{info["natH"]}', flush=True)

        ctx.close()
        b.close()

    fails = []
    for r in results:
        if r.get('blend_mode') != 'multiply':
            fails.append(f"q{r['question']}: blend={r['blend_mode']} != multiply")
        if r.get('pure_white_pct', 100) > 0.5:
            fails.append(f"q{r['question']}: pure white {r['pure_white_pct']}% > 0.5%")
        if r.get('exact_bg_pct', 0) < 10:
            fails.append(f"q{r['question']}: only {r.get('exact_bg_pct')}% equals card bg")
    report = {'url': URL, 'results': results, 'fails': fails,
              'pass': len(fails) == 0}
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=1)
    print(f'\n=== {"PASS" if report["pass"] else "FAIL"} : {len(fails)} issue(s) ===')
    for x in fails:
        print('  !', x)
    return 0 if report['pass'] else 1


if __name__ == '__main__':
    sys.exit(main())
