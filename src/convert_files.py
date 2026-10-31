#!/usr/bin/env python3
"""Convert raw mmx PNGs -> cropped, squared, opaque WebP -> individual FILES.

Same pipeline as convert.py (crop white -> square on white -> 384px WebP q86),
but writes `assets/img/NN.webp` on disk instead of base64 into b64.json.

Emits `assets/img/manifest.json`:
  {"1": {"word": "...", "cat": "...", "file": "assets/img/01.webp",
         "bytes": 12345, "fallback": false}, ...}

A question whose source is missing/empty falls back to the emoji in
questions.json and is marked "fallback": true — never silently faked.

Usage: convert_files.py <out_root>   (assets/img/ is created under it)
"""
import os, io, json, sys
from PIL import Image

BASE = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(BASE, 'imgs', 'raw')

WHITE_THRESH = 246
SIZE = 384
QUALITY = 86
MIN_BYTES = 5000


def crop_content(img, thresh=WHITE_THRESH):
    rgb = img.convert('RGB')
    px = rgb.load()
    w, h = rgb.size
    mask = Image.new('L', (w, h), 0)
    mp = mask.load()
    for y in range(h):
        for x in range(w):
            r, g, b = px[x, y]
            if not (r > thresh and g > thresh and b > thresh):
                mp[x, y] = 255
    bbox = mask.getbbox()
    return rgb.crop(bbox) if bbox else rgb


def square_on_white(img, size=SIZE, margin=1.06):
    w, h = img.size
    side = int(max(w, h) * margin)
    canvas = Image.new('RGB', (side, side), (255, 255, 255))
    canvas.paste(img, ((side - w) // 2, (side - h) // 2))
    return canvas.resize((size, size), Image.LANCZOS)


def convert_one(n, size=SIZE, quality=QUALITY):
    """Return (bytes|None, reason). None => caller must use emoji fallback."""
    src = os.path.join(RAW, f'{n:02d}.png')
    if not os.path.exists(src):
        return None, 'no-source'
    if os.path.getsize(src) < MIN_BYTES:
        return None, f'small-source({os.path.getsize(src)}B)'
    try:
        img = Image.open(src)
        img.load()
    except Exception as e:                       # corrupt PNG -> fallback
        return None, f'decode-fail({type(e).__name__})'
    if img.width != img.height:
        s = min(img.size)
        img = img.crop(((img.width - s) // 2, (img.height - s) // 2,
                        (img.width + s) // 2, (img.height + s) // 2))
    img = square_on_white(crop_content(img), size)
    buf = io.BytesIO()
    img.save(buf, 'WEBP', quality=quality, method=6)
    data = buf.getvalue()
    if len(data) < 500:
        return None, f'empty-webp({len(data)}B)'
    return data, 'ok'


def main():
    if len(sys.argv) < 2:
        print('usage: convert_files.py <out_root>')
        return 2
    out_root = os.path.abspath(sys.argv[1])
    img_dir = os.path.join(out_root, 'assets', 'img')
    os.makedirs(img_dir, exist_ok=True)

    questions = json.load(open(os.path.join(BASE, 'questions.json')))
    manifest, ok, fail, total = {}, [], [], 0
    for q in questions:
        n = q['n']
        data, why = convert_one(n)
        rel = f'assets/img/{n:02d}.webp'
        entry = {'word': q['word'], 'cat': q['cat'], 'file': rel,
                 'emoji': q.get('emoji', ''), 'fallback': True, 'reason': why}
        if data:
            with open(os.path.join(out_root, rel), 'wb') as f:
                f.write(data)
            total += len(data)
            entry.update({'bytes': len(data), 'fallback': False, 'reason': 'ok'})
            ok.append(n)
            print(f'{n:02d} OK   {len(data)//1024:4d}KB  {q["word"]}', flush=True)
        else:
            fail.append((n, q['word'], why))
            print(f'{n:02d} FALLBACK {why}  {q["word"]}', flush=True)
        manifest[str(n)] = entry

    with open(os.path.join(img_dir, 'manifest.json'), 'w', encoding='utf-8') as f:
        json.dump(manifest, f, ensure_ascii=False, indent=1)

    print(f'\n=== wrote {len(ok)}/{len(questions)} webp files, '
          f'{len(fail)} emoji-fallback ===')
    print(f'total webp payload : {total/1024:.0f} KB')
    if fail:
        print('FALLBACK (emoji used in HTML):')
        for n, w, why in fail:
            print(f'  {n:02d} {w}  ({why})')
    return 0


if __name__ == '__main__':
    sys.exit(main())
