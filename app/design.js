/* Draws one of the 200 Kenney crosshairs from its real outlines (see designs.js).
   Because the shapes are geometry, the sliders are exact:
     e   > 0  strokes grow by e px each side, e < 0 strokes shrink by -e px each side
     off > 0  arms and corner pieces slide outward by off px, off < 0 inward (centre gap)
     hole     radius of a hole cut in the middle (designs with no separate arms)  */
var designCache = {}, designCacheN = 0;
var designPaths = {};

function designHasArms(idx) {
  var d = DESIGNS[idx];
  for (var i = 0; i < d.length; i++) if (d[i][1]) return true;
  return false;
}

function makeDesign(idx, colour, side, e, off, hole) {
  var key = [idx, colour, side, e.toFixed(2), off.toFixed(1), hole.toFixed(1)].join("|");
  if (designCache[key]) return designCache[key];
  var d = DESIGNS[idx];
  if (!d) return null;
  var k = side / 64, pad = Math.ceil(Math.max(e, 0)) + Math.ceil(Math.max(off, 0)) + 3;
  var c = document.createElement("canvas");
  c.width = c.height = side + 2 * pad;   // side is even, so the canvas centre is a whole pixel
  var g = c.getContext("2d");
  g.translate(pad + side / 2, pad + side / 2);
  g.scale(k, k); g.translate(-32, -32);
  var eu = e / k, ou = off / k, hu = hole / k;
  g.fillStyle = colour; g.strokeStyle = colour;
  g.lineJoin = "miter"; g.miterLimit = 2;
  var items = d.map(function (it) {
    var p = designPaths[it[0]] || (designPaths[it[0]] = new Path2D(it[0]));
    var mv = it[1], dx = 0, dy = 0;
    if (mv && mv[0] === "b") {
      var o = Math.max(ou, -mv[3]);                    // an arm stops at the centre
      if (mv[1] === "x") dx = mv[2] * o; else dy = mv[2] * o;
    } else if (mv && mv[0] === "c") {
      dx = mv[1] * ou * 0.7071; dy = mv[2] * ou * 0.7071;
    }
    return { p: p, dx: dx, dy: dy };
  });
  items.forEach(function (it) {
    g.save(); g.translate(it.dx, it.dy); g.fill(it.p);
    if (eu > 0) { g.lineWidth = 2 * eu; g.stroke(it.p); }
    g.restore();
  });
  if (eu < 0) {
    g.globalCompositeOperation = "destination-out";
    g.lineWidth = -2 * eu;
    items.forEach(function (it) { g.save(); g.translate(it.dx, it.dy); g.stroke(it.p); g.restore(); });
  }
  if (hu > 0) {
    g.globalCompositeOperation = "destination-out";
    g.beginPath(); g.arc(32, 32, hu, 0, 6.2832); g.fill();
  }
  if (designCacheN++ > 80) { designCache = {}; designCacheN = 0; }
  designCache[key] = c;
  return c;
}

/* Draws design idx centred on (cx, cy). s = pixels per layout unit; cfg = the reticle settings. */
function drawDesign(ctx, idx, cx, cy, cfg, s) {
  var side = 2 * Math.max(4, Math.round(cfg.size * 1.2 * s));   // even, so the art sits on whole pixels
  var k = side / 64;
  var th = cfg.thickness;
  // thickness 3 is the pack's own line weight
  // thinner than 3 erodes by up to this design's calibrated amount (the most it can lose and keep 40% of its ink)
  var hw = (typeof DESIGN_HW !== "undefined" && DESIGN_HW[idx]) || 0.5;
  var e = th >= 3 ? (th - 3) * 0.5 * s : -Math.min(3 - th, 2) / 2 * hw * k;
  var arms = designHasArms(idx);
  var gapPx = (cfg.gap - 10) * s;                      // gap 10 = the picture as drawn
  var off = arms ? gapPx : 0;
  var hole = !arms && gapPx > 0 ? Math.min(gapPx, 0.6 * (DESIGN_R[idx] || 32) * k) : 0;
  if (typeof DESIGN_SHIFT !== "undefined" && DESIGN_SHIFT[idx]) cy += DESIGN_SHIFT[idx] * k;   // aim point is the tip, not the grid centre
  var fill = makeDesign(idx, cfg.color, side, e, off, hole);
  if (!fill) return false;
  var fx = Math.round(cx) - fill.width / 2, fy = Math.round(cy) - fill.height / 2;
  if (cfg.outline) {
    var o = Math.max(1, Math.round(s));
    var dark = makeDesign(idx, "#000000", side, e + o, off, hole);
    var dx = Math.round(cx) - dark.width / 2, dy = Math.round(cy) - dark.height / 2;
    ctx.drawImage(dark, dx, dy);
  }
  ctx.drawImage(fill, fx, fy);
  return true;
}
