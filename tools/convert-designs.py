#!/usr/bin/env python3
"""Turn the 200 Kenney SVG crosshairs (64x64 grid) into parametric primitives.

bar   [ax, dir, inner, outer, c, w]   axis-aligned rectangle running along ax ("x"/"y")
                                     from centre+dir*inner to centre+dir*outer, centre line c, width w
rbar  same, but 'radial' (centre line on the middle, one end nearer the middle): gap slides `inner`
disc  [cx, cy, r]
ring  [cx, cy, ro, ri]
poly  [d]                            anything else, drawn as is (offset for thickness)
corner groups: bars/polys that touch each other and sit in a corner are moved together by `gap`.
"""
import re, glob, json, math, sys, os
C = 32.0

def subpaths(d):
    out = []
    for m in re.finditer(r'M([^M]*)', d):
        body = m.group(1)
        segs = re.findall(r'[LQ]?[^LQ]+', body)
        pts = []; kinds = set()
        first = True
        for seg in segs:
            k = seg[0] if seg[0] in 'LQ' else 'M'
            nums = [float(x) for x in re.findall(r'-?\d+\.?\d*', seg)]
            if first:
                pts.append((nums[0], nums[1])); nums = nums[2:]; first = False
                if not nums: continue
            kinds.add(k)
            step = 4 if k == 'Q' else 2
            for i in range(0, len(nums), step):
                pts.append((nums[i + step - 2], nums[i + step - 1]))
        out.append(('M' + body.strip(), pts, kinds))
    return out

def signed_area(pts):
    return sum(pts[i][0] * pts[(i + 1) % len(pts)][1] - pts[(i + 1) % len(pts)][0] * pts[i][1] for i in range(len(pts))) / 2

def classify(sp):
    d, pts, kinds = sp
    xs = [p[0] for p in pts]; ys = [p[1] for p in pts]
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    if kinds == {'Q'}:
        r = (x1 - x0) / 2; cx = (x0 + x1) / 2; cy = (y0 + y1) / 2
        if abs((y1 - y0) / 2 - r) < .05 and all(abs(math.hypot(x - cx, y - cy) - r) < .15 for x, y in pts):
            return ('circle', cx, cy, r, signed_area(pts))
    if kinds == {'L'} and len(pts) in (4, 5):
        ux = sorted(set(round(x, 3) for x in xs)); uy = sorted(set(round(y, 3) for y in ys))
        if len(ux) == 2 and len(uy) == 2 and abs((x1 - x0) - (y1 - y0)) > 1e-6:
            return ('rect', x0, y0, x1, y1)
    return ('poly', d, x0, y0, x1, y1)

def touches(a, b):
    return not (a[2] < b[0] - .01 or b[2] < a[0] - .01 or a[3] < b[1] - .01 or b[3] < a[1] - .01)

def convert(svg):
    """-> list of [path_d, move]. move: null (stays), ["b", axis, dir, inner] (arm that slides
    along its axis with the gap), ["c", sx, sy] (corner piece that slides diagonally)."""
    items = []                                   # dict(d, bb, mv)
    for d in re.findall(r' d="([^"]*)"', svg):
        subs = subpaths(d); cls = [classify(sp) for sp in subs]
        def inside(a, b):                         # bbox of a sits inside bbox of b
            return a[0] >= b[0] - .01 and a[1] >= b[1] - .01 and a[2] <= b[2] + .01 and a[3] <= b[3] + .01
        bbs_ = [(min(pt[0] for pt in sp[1]), min(pt[1] for pt in sp[1]), max(pt[0] for pt in sp[1]), max(pt[1] for pt in sp[1])) for sp in subs]
        nested = any(i != j and inside(bbs_[i], bbs_[j]) for i in range(len(subs)) for j in range(len(subs)))
        if nested or any(c[0] == 'circle' for c in cls):   # rings / holes: keep the whole path together
            xs = [pt[0] for sp in subs for pt in sp[1]]; ys = [pt[1] for sp in subs for pt in sp[1]]
            items.append(dict(d=' '.join(sp[0] + ' Z' for sp in subs), bb=(min(xs), min(ys), max(xs), max(ys)), mv=None, fixed=True))
            continue
        for sp, c in zip(subs, cls):
            xs = [pt[0] for pt in sp[1]]; ys = [pt[1] for pt in sp[1]]
            it = dict(d=sp[0] + ' Z', bb=(min(xs), min(ys), max(xs), max(ys)), mv=None, fixed=False)
            if c[0] == 'rect':
                x0, y0, x1, y1 = c[1:]
                horiz = (x1 - x0) > (y1 - y0)
                cen = (y0 + y1) / 2 if horiz else (x0 + x1) / 2
                lo, hi = (x0 - C, x1 - C) if horiz else (y0 - C, y1 - C)
                if abs(cen - C) < .6 and (lo >= -.01 or hi <= .01):
                    sign = 1 if lo >= -.01 else -1
                    it['mv'] = ['b', 'x' if horiz else 'y', sign, round(lo if sign > 0 else -hi, 3)]
                    it['fixed'] = True
            items.append(it)
    free = [i for i, it in enumerate(items) if not it['fixed']]
    parent = {i: i for i in free}
    def find(i):
        while parent[i] != i: parent[i] = parent[parent[i]]; i = parent[i]
        return i
    for a_ in free:
        for b_ in free:
            if a_ < b_ and touches(items[a_]['bb'], items[b_]['bb']): parent[find(a_)] = find(b_)
    groups = {}
    for i in free: groups.setdefault(find(i), []).append(i)
    for idx in groups.values():
        bbs = [items[i]['bb'] for i in idx]
        mx = (min(b[0] for b in bbs) + max(b[2] for b in bbs)) / 2 - C
        my = (min(b[1] for b in bbs) + max(b[3] for b in bbs)) / 2 - C
        if abs(mx) > 6 and abs(my) > 6:
            for i in idx: items[i]['mv'] = ['c', 1 if mx > 0 else -1, 1 if my > 0 else -1]
    seen = set(); out = []
    for it in items:                              # the SVGs repeat some layers; keep one of each
        key = (it['d'], json.dumps(it['mv']))
        if key not in seen: seen.add(key); out.append([it['d'], it['mv']])
    return out

if __name__ == '__main__':
    data = [convert(open(f).read()) for f in sorted(glob.glob('assets/kenney-svg/*.svg'))]
    kinds = {'slide arm': 0, 'corner piece': 0, 'fixed': 0}
    moving_designs = 0
    for d in data:
        mv = [m for _, m in d]
        kinds['slide arm'] += sum(1 for m in mv if m and m[0] == 'b')
        kinds['corner piece'] += sum(1 for m in mv if m and m[0] == 'c')
        kinds['fixed'] += sum(1 for m in mv if not m)
        moving_designs += any(mv)
    print(kinds, "designs where the gap does something:", moving_designs, "of", len(data))
    print("designs with nothing movable:", [i for i, d in enumerate(data) if not any(m for _, m in d)])
    out = '/* generated by tools/convert-designs.py from the Kenney Crosshair Pack (CC0) */\nvar DESIGNS = ' \
          + json.dumps(data, separators=(',', ':')) + ';\n'
    import math as _m
    rad = []
    for d in data:
        r = 1.0
        for path, _mv in d:
            nums = [float(x) for x in re.findall(r'-?\d+\.?\d*', path)]
            for i in range(0, len(nums) - 1, 2):
                r = max(r, _m.hypot(nums[i] - C, nums[i + 1] - C))
        rad.append(round(r, 1))
    out += 'var DESIGN_R = ' + json.dumps(rad, separators=(',', ':')) + ';\n'
    # designs whose aim point is a tip, not the grid centre: slide the art so the tip lands on the screen centre
    shift = {}
    for i in (95, 96, 97, 98):                   # upward arrows: tip = topmost point
        ys = [float(v) for path, _m in data[i] for v in re.findall(r'-?\d+\.?\d*', path)[1::2]]
        shift[i] = round(C - min(ys), 2)
    shift[3] = round(C - (28 + 36 + 28) / 3.0, 2)  # three dots at y 28, 36, 28: aim at their midpoint
    shift[99] = round(C - 18.0, 2)                  # T: aim at the middle of the top bar (y 16..20)
    shift[150] = round(C - 17.0, 2)                 # T: aim at the middle of the top bar (y 16..18)
    out += 'var DESIGN_SHIFT = ' + json.dumps(shift) + ';\n'
    hwf = 'assets/design-halfwidths.json'      # thinnest stroke per design, measured in a browser (see README)
    if os.path.exists(hwf):
        out += 'var DESIGN_HW = ' + open(hwf).read().strip() + ';\n'
    open('app/designs.js', 'w').write(out)
    print(len(out), "bytes")
