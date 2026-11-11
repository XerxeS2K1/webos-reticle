#!/usr/bin/env python3
"""Reticle phone page - a thin front end for org.hermes.reticle.service.

The settings live in the webOS service (the same one the on-TV Reticle app
talks to), so this process keeps no state of its own: every request is
forwarded over the luna bus with luna-send. One source of truth, two ways in:
the remote on the TV, or this page from a phone on the same network.
"""
import json
import os
import shlex
import subprocess
import threading
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT = 8765
LOG = "/tmp/reticle-control.log"
SERVICE = "org.hermes.reticle.service"


def log(msg):
    try:
        with open(LOG, "a") as fh:
            fh.write("%s %s\n" % (time.strftime("%H:%M:%S"), msg))
    except Exception:
        pass


import time  # noqa: E402  (kept next to log for readability above)


def luna(method, payload=None, timeout=8):
    """Call our luna service and return its reply payload (dict)."""
    cmd = "luna-send -n 1 -f luna://%s/%s %s" % (
        SERVICE, method, shlex.quote(json.dumps(payload or {})))
    res = subprocess.run(["script", "-q", "-c", cmd, "/dev/null"],
                         capture_output=True, text=True, timeout=timeout)
    out = (res.stdout or "").strip()
    start = out.find("{")
    if start < 0:
        raise RuntimeError("no reply: %s" % (out or res.stderr or "empty"))
    reply, _ = json.JSONDecoder().raw_decode(out[start:])
    if not reply.get("returnValue", True):
        raise RuntimeError(reply.get("errorText") or "service error")
    return reply


BACKUP = "/media/developer/reticle-backup.json"   # outside the app package, survives reinstalls
FACTORY = {"style": "cross", "size": 26, "gap": 10, "thickness": 3, "color": "#00ff88",
           "opacity": 0.9, "dot": 2, "outline": True, "dx": 0, "dy": 0, "grid": False, "image": -1}


def save_backup(st):
    try:
        keep = {"enabled": bool(st.get("enabled")), "inputs": st.get("inputs") or [],
                "reticle": st.get("reticle") or {}}
        with open(BACKUP + ".tmp", "w") as fh:
            json.dump(keep, fh)
        os.replace(BACKUP + ".tmp", BACKUP)
    except Exception as exc:
        log("backup failed: %r" % (exc,))


def restore_if_reset(st):
    """A reinstall wipes the service's own state file. If the service now looks
    factory-fresh and we hold a different saved copy, put that copy back."""
    try:
        r = st.get("reticle") or {}
        fresh = all(r.get(k) == v for k, v in FACTORY.items() if k != "image") \
            and r.get("image", -1) == -1 and st.get("inputs") == ["com.webos.app.hdmi1"] \
            and st.get("enabled") is True
        if not fresh or not os.path.exists(BACKUP):
            return
        with open(BACKUP) as fh:
            saved = json.load(fh)
        fresh_copy = {"enabled": True, "inputs": ["com.webos.app.hdmi1"], "reticle": dict(r)}
        if saved != fresh_copy and saved.get("reticle"):
            luna("putState", saved)
            log("service state was reset - restored saved settings")
    except Exception as exc:
        log("restore failed: %r" % (exc,))


def own_url():
    """Address a phone on the same network can open (no packets are sent)."""
    import socket
    try:
        sk = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sk.connect(("192.0.2.1", 9))
        ip = sk.getsockname()[0]
        sk.close()
    except Exception:
        ip = "TV-IP"
    return "http://%s:%d" % (ip, PORT)


def flat_state():
    reply = luna("getState")
    state = reply.get("state") or {}
    out = {
        "enabled": state.get("enabled", True),
        "inputs": state.get("inputs", []),
        "reticle": state.get("reticle", {}),
        "available": reply.get("available", []),
        "url": own_url(),
    }
    if state.get("report"):
        out["report"] = state["report"]
    return out


PAGE = r"""<!DOCTYPE html>
<html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>Reticle</title>
<style>
:root { color-scheme: dark; }
* { box-sizing: border-box; -webkit-tap-highlight-color: transparent; }
body { margin: 0; padding: 18px 16px 40px; background: #0d1012; color: #e6edf3;
       font: 16px/1.4 -apple-system, "Segoe UI", Roboto, sans-serif; }
h1 { font-size: 19px; margin: 0 0 2px; font-weight: 600; }
.sub { color: #7d8894; font-size: 13px; margin-bottom: 20px; }
.card { background: #151a1e; border: 1px solid #232a30; border-radius: 14px;
        padding: 16px; margin-bottom: 14px; }
.row { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
.row + .row { margin-top: 14px; }
label.name { font-size: 14px; color: #b9c4cf; }
.val { font-variant-numeric: tabular-nums; color: #6fe3a4; font-size: 14px; min-width: 3.2em; text-align: right; }
input[type=range] { -webkit-appearance: none; width: 100%; height: 30px; background: transparent; }
input[type=range]::-webkit-slider-runnable-track { height: 4px; background: #2b343c; border-radius: 2px; }
input[type=range]::-webkit-slider-thumb { -webkit-appearance: none; width: 26px; height: 26px; margin-top: -11px;
        border-radius: 50%; background: #6fe3a4; border: none; }
.power { display: flex; align-items: center; gap: 14px; }
.switch { position: relative; width: 62px; height: 34px; flex: 0 0 auto; }
.switch input { opacity: 0; width: 100%; height: 100%; margin: 0; position: absolute; z-index: 2; }
.track { position: absolute; inset: 0; background: #2b343c; border-radius: 17px; transition: .18s; }
.track::after { content: ""; position: absolute; top: 3px; left: 3px; width: 28px; height: 28px;
        border-radius: 50%; background: #8b96a2; transition: .18s; }
.switch input:checked + .track { background: #1d5c3d; }
.switch input:checked + .track::after { transform: translateX(28px); background: #6fe3a4; }
.swatches { display: flex; gap: 10px; flex-wrap: wrap; }
.sw { width: 38px; height: 38px; border-radius: 10px; border: 2px solid #232a30; }
.sw.on { border-color: #e6edf3; }
input[type=color] { width: 46px; height: 38px; padding: 0; border: 2px solid #232a30;
        border-radius: 10px; background: #151a1e; }
.styles { display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; }
.styles button { padding: 11px 4px; font-size: 13px; border-radius: 10px; border: 1px solid #232a30;
        background: #11161a; color: #b9c4cf; }
.styles button.on { border-color: #6fe3a4; color: #6fe3a4; background: #12201a; }
.pick { display: flex; flex-wrap: wrap; gap: 4px; max-height: 360px; overflow-y: auto;
        margin-top: 10px; -webkit-overflow-scrolling: touch; }
.pk { width: 58px; height: 67px; border: 2px solid transparent; border-radius: 8px;
      background: #26364a url(/crosshairs.png) no-repeat; background-size: 1152px 672px; }
.pk.on { border-color: #6fe3a4; }
.wheelbox { position: relative; width: 240px; height: 240px; margin: 4px auto 14px; touch-action: none; }
.wheelbox canvas { width: 240px; height: 240px; border-radius: 50%; display: block; }
#wshade { position: absolute; inset: 0; border-radius: 50%; background: #000; pointer-events: none; }
#wknob { position: absolute; width: 26px; height: 26px; margin: -13px 0 0 -13px; border-radius: 50%;
         border: 3px solid #fff; box-shadow: 0 0 0 1.5px #0008, inset 0 0 0 1.5px #0008; pointer-events: none; }
input[type=range].bright { -webkit-appearance: none; appearance: none; height: 22px; border-radius: 11px;
         width: 100%; margin: 4px 0 12px; background: linear-gradient(90deg, #000, #fff); }
input[type=range].bright::-webkit-slider-thumb { -webkit-appearance: none; width: 28px; height: 28px;
         border-radius: 50%; background: #fff; border: 3px solid #0008; }
.hexv { text-align: center; font-size: 14px; color: #8b96a2; margin-bottom: 10px; font-variant-numeric: tabular-nums; }
.inputs label { display: flex; align-items: center; gap: 10px; padding: 9px 0; font-size: 15px; }
.inputs input { width: 20px; height: 20px; accent-color: #6fe3a4; }
.foot { display: flex; align-items: center; justify-content: space-between; margin-top: 4px; }
.toast { font-size: 13px; color: #6fe3a4; opacity: 0; transition: opacity .25s; }
.toast.show { opacity: 1; }
button.reset { background: none; border: 1px solid #2b343c; color: #8b96a2; font-size: 13px;
        padding: 8px 14px; border-radius: 10px; }
</style></head>
<body>
<h1>Reticle</h1>
<div class="sub">Overlay control &middot; changes apply live</div>

<div class="card">
  <div class="power">
    <div class="switch"><input type="checkbox" id="enabled"><span class="track"></span></div>
    <div><div style="font-size:15px">Show the reticle</div>
         <div style="font-size:13px;color:#7d8894" id="stateHint">on the selected inputs</div></div>
  </div>
</div>

<div class="card">
  <div class="row"><label class="name" for="color">Colour</label></div>
  <div class="wheelbox" id="wheel"><canvas id="wcv"></canvas><div id="wshade"></div><div id="wknob"></div></div>
  <input type="range" class="bright" id="bright" min="0" max="100" step="1">
  <div class="hexv" id="hexv"></div>
  <div class="row"><div class="swatches" id="swatches"></div></div>
</div>

<div class="card" id="sliders">
  <div class="row"><label class="name" for="size">Size</label><span class="val" id="size_v"></span></div>
  <input type="range" id="size" min="4" max="70" step="1">
  <div class="row"><label class="name" for="gap">Centre gap</label><span class="val" id="gap_v"></span></div>
  <input type="range" id="gap" min="0" max="40" step="1">
  <div class="row"><label class="name" for="thickness">Thickness</label><span class="val" id="thickness_v"></span></div>
  <input type="range" id="thickness" min="1" max="10" step="1">
  <div class="row"><label class="name" for="opacity">Opacity</label><span class="val" id="opacity_v"></span></div>
  <input type="range" id="opacity" min="10" max="100" step="5">
  <div class="row"><label class="name" for="dot">Centre dot</label><span class="val" id="dot_v"></span></div>
  <input type="range" id="dot" min="0" max="8" step="1">
  <div class="row"><label class="name" for="dx">Offset X</label><span class="val" id="dx_v"></span></div>
  <input type="range" id="dx" min="-200" max="200" step="1">
  <div class="row"><label class="name" for="dy">Offset Y</label><span class="val" id="dy_v"></span></div>
  <input type="range" id="dy" min="-200" max="200" step="1">
</div>

<div class="card">
  <div class="row"><label class="name">Shape</label></div>
  <div class="styles" id="styles">
    <button data-style="cross">Cross</button>
    <button data-style="dot">Dot</button>
    <button data-style="circle">Circle</button>
    <button data-style="t">T mark</button>
    <button data-style="corners">Corners</button>
    <button data-style="brackets">Brackets</button>
  </div>
</div>

<div class="card">
  <div class="row"><label class="name">Design (200 to pick from)</label><span id="image_v" style="color:#8b96a2;font-size:13px">built-in</span></div>
  <div class="sub" style="margin:6px 0 0">Tap any picture. Colour, size and opacity still apply. Tap a shape above to go back to the built-in ones.</div>
  <div class="pick" id="pick"></div>
</div>

<div class="card">
  <div class="row">
    <label class="name" for="grid">Test pattern</label>
    <input type="checkbox" id="grid" style="width:22px;height:22px;accent-color:#6fe3a4">
  </div>
  <div class="sub" style="margin:8px 0 0">Magenta lines mark the panel centre; white marks sit on the panel edges. Use it to check centring and overscan, then switch it off.</div>
</div>

<div class="card inputs" id="inputs"></div>

<div class="foot">
  <button class="reset" id="reset">Reset defaults</button>
  <span class="toast" id="toast">saved</span>
</div>

<script>
function hexToHsv(hex) {
  const m = /^#?([0-9a-f]{6})$/i.exec(hex || ""); if (!m) return [0, 0, 1];
  const n = parseInt(m[1], 16), r = (n >> 16 & 255) / 255, g = (n >> 8 & 255) / 255, b = (n & 255) / 255;
  const mx = Math.max(r, g, b), mn = Math.min(r, g, b), d = mx - mn;
  let h = 0;
  if (d) h = mx === r ? ((g - b) / d + 6) % 6 : mx === g ? (b - r) / d + 2 : (r - g) / d + 4;
  return [h * 60, mx ? d / mx : 0, mx];
}
function hsvToHex(h, s, v) {
  h = ((h % 360) + 360) % 360;
  const f = n => { const k = (n + h / 60) % 6; return v - v * s * Math.max(0, Math.min(k, 4 - k, 1)); };
  const x = n => Math.round(f(n) * 255).toString(16).padStart(2, "0");
  return "#" + x(5) + x(3) + x(1);
}
let hsv = [140, 1, 1];
(function () {
  const cv = document.getElementById("wcv"), N = Math.round(240 * (window.devicePixelRatio || 1));
  cv.width = cv.height = N;
  const g = cv.getContext("2d"), img = g.createImageData(N, N), R = N / 2;
  for (let y = 0; y < N; y++) for (let x = 0; x < N; x++) {
    const dx = x + 0.5 - R, dy = y + 0.5 - R, d = Math.hypot(dx, dy), i = (y * N + x) * 4;
    if (d > R) continue;
    const h = (Math.atan2(dy, dx) * 180 / Math.PI + 90 + 360) % 360;      // red at the top
    const c = hsvToHex(h, Math.min(1, d / R), 1), n = parseInt(c.slice(1), 16);
    img.data[i] = n >> 16 & 255; img.data[i + 1] = n >> 8 & 255; img.data[i + 2] = n & 255;
    img.data[i + 3] = d > R - 1 ? Math.round(255 * (R - d)) : 255;
  }
  g.putImageData(img, 0, 0);
  const box = document.getElementById("wheel");
  const pick = e => {
    const b = box.getBoundingClientRect(), dx = e.clientX - b.left - 120, dy = e.clientY - b.top - 120;
    hsv[0] = (Math.atan2(dy, dx) * 180 / Math.PI + 90 + 360) % 360;
    hsv[1] = Math.min(1, Math.hypot(dx, dy) / 120);
    if (hsv[2] < 0.05) hsv[2] = 1;
    paintColour(true);
  };
  let down = false;
  box.addEventListener("pointerdown", e => { down = true; box.setPointerCapture(e.pointerId); pick(e); });
  box.addEventListener("pointermove", e => { if (down) pick(e); });
  box.addEventListener("pointerup", () => { down = false; });
  box.addEventListener("pointercancel", () => { down = false; });
  document.getElementById("bright").addEventListener("input", e => { hsv[2] = e.target.value / 100; paintColour(true); });
})();
function paintColour(send) {
  const hex = hsvToHex(hsv[0], hsv[1], hsv[2]);
  const a = (hsv[0] - 90) * Math.PI / 180;
  const k = document.getElementById("wknob");
  k.style.left = (120 + Math.cos(a) * hsv[1] * 120) + "px";
  k.style.top = (120 + Math.sin(a) * hsv[1] * 120) + "px";
  k.style.background = hex;
  document.getElementById("wshade").style.opacity = 1 - hsv[2];
  const b = document.getElementById("bright");
  b.value = Math.round(hsv[2] * 100);
  b.style.background = "linear-gradient(90deg,#000," + hsvToHex(hsv[0], hsv[1], 1) + ")";
  document.getElementById("hexv").textContent = hex.toUpperCase();
  if (send) reticle({color: hex});
}
const PRESETS = ["#00ff88", "#ff2d55", "#ffffff", "#00d5ff", "#ffd60a"];
let state = null, timer = null;

function toast(msg) {
  const t = document.getElementById("toast");
  t.textContent = msg || "saved";
  t.classList.add("show");
  clearTimeout(toast._t);
  toast._t = setTimeout(() => t.classList.remove("show"), 900);
}

function put(partial) {
  state = Object.assign({}, state, partial);
  clearTimeout(timer);
  timer = setTimeout(async () => {
    try {
      const r = await fetch("/api/state", {method: "POST", body: JSON.stringify(state)});
      state = await r.json();
      toast("saved");
    } catch (e) { toast("TV not answering"); }
  }, 120);
}

function reticle(patch) {
  put({reticle: Object.assign({}, state.reticle, patch)});
}

function render() {
  document.getElementById("enabled").checked = !!state.enabled;
  const r = state.reticle;
  document.getElementById("stateHint").textContent = state.enabled
    ? "on " + (state.inputs.length ? "selected inputs" : "no input yet")
    : "off everywhere";
  if (hsvToHex(hsv[0], hsv[1], hsv[2]) !== String(r.color).toLowerCase()) {
    const n = hexToHsv(r.color);              // keep the old hue when grey/black hides it
    hsv = [n[1] && n[2] ? n[0] : hsv[0], n[1], n[2]];
  }
  paintColour(false);
  document.getElementById("grid").checked = !!r.grid;
  document.querySelectorAll("#swatches .sw").forEach(el =>
    el.classList.toggle("on", el.dataset.c.toLowerCase() === String(r.color).toLowerCase()));
  const im = (r.image === undefined || r.image === null) ? -1 : r.image;
  document.querySelectorAll("#styles button").forEach(el =>
    el.classList.toggle("on", im < 0 && el.dataset.style === r.style));
  document.querySelectorAll("#pick .pk").forEach(el =>
    el.classList.toggle("on", Number(el.dataset.i) === im));
  document.getElementById("image_v").textContent = im < 0 ? "built-in" : "#" + im;
  document.querySelectorAll("#inputs input").forEach(el =>
    el.checked = state.inputs.includes(el.value));
  for (const k of ["size", "gap", "thickness", "dot", "dx", "dy"]) {
    document.getElementById(k).value = r[k];
    document.getElementById(k + "_v").textContent = r[k];
  }
  const op = Math.round(r.opacity * 100);
  document.getElementById("opacity").value = op;
  document.getElementById("opacity_v").textContent = op + "%";
}

async function init() {
  const r = await fetch("/api/state");
  state = await r.json();
  const sw = document.getElementById("swatches");
  sw.innerHTML = "";
  for (const c of PRESETS) {
    const d = document.createElement("div");
    d.className = "sw"; d.dataset.c = c; d.style.background = c;
    d.onclick = () => { hsv = hexToHsv(c); paintColour(false); reticle({color: c}); render(); };
    sw.appendChild(d);
  }
  const box = document.getElementById("inputs");
  box.innerHTML = '<div class="row"><label class="name">Show on</label></div>';
  for (const [id, label] of state.available) {
    const l = document.createElement("label");
    const cb = document.createElement("input");
    cb.type = "checkbox"; cb.value = id;
    cb.onchange = () => {
      const on = state.inputs.filter(x => x !== id);
      if (cb.checked) on.push(id);
      put({inputs: on});
    };
    l.appendChild(cb); l.appendChild(document.createTextNode(label));
    box.appendChild(l);
  }
  render();
}

document.getElementById("enabled").onchange = e => { put({enabled: e.target.checked}); render(); };
document.getElementById("grid").onchange = e => reticle({grid: e.target.checked});
for (const k of ["size", "gap", "thickness", "dot", "dx", "dy"]) {
  document.getElementById(k).oninput = e => {
    const v = parseInt(e.target.value, 10);
    document.getElementById(k + "_v").textContent = v;
    reticle({[k]: v});
  };
}
document.getElementById("opacity").oninput = e => {
  const v = parseInt(e.target.value, 10);
  document.getElementById("opacity_v").textContent = v + "%";
  reticle({opacity: v / 100});
};
document.querySelectorAll("#styles button").forEach(el =>
  el.onclick = () => { reticle({style: el.dataset.style, image: -1}); render(); });
(function () {
  const pick = document.getElementById("pick");
  for (let i = 0; i < 200; i++) {
    const b = document.createElement("div");
    b.className = "pk"; b.dataset.i = i;
    b.style.backgroundPosition = "-" + ((i % 20) * 57.6) + "px -" + (Math.floor(i / 20) * 67.2) + "px";
    b.onclick = () => { reticle({image: i}); render(); };
    pick.appendChild(b);
  }
})();
document.getElementById("reset").onclick = () => put({reticle: {style:"cross",size:26,gap:10,thickness:3,color:"#00ff88",opacity:0.9,dot:2,outline:true,dx:0,dy:0,grid:false,image:-1}});

init();
</script>
</body></html>
"""


class Handler(BaseHTTPRequestHandler):
    server_version = "reticle-control"

    def _send(self, code, body, ctype="application/json"):
        if isinstance(body, (dict, list)):
            body = json.dumps(body)
        if isinstance(body, str):
            body = body.encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "*")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self._send(204, b"")

    def do_GET(self):
        path = self.path.split("?")[0]
        if path in ("/", "/index.html"):
            # who opened the page - tells us whether a phone is reaching us at all
            log("page opened by %s (%s)" % (self.client_address[0], (self.headers.get("User-Agent") or "?")[:70]))
            self._send(200, PAGE, "text/html; charset=utf-8")
            return
        if path == "/crosshairs.png":
            try:
                with open("/media/developer/crosshairs-sheet.png", "rb") as fh:
                    self._send(200, fh.read(), "image/png")
            except Exception:
                self._send(404, {"error": "no sheet"})
            return
        if path == "/healthz":
            self._send(200, {"ok": True})
            return
        if path in ("/api/state", "/api/reticle.json"):
            try:
                self._send(200, flat_state())
            except Exception as exc:
                self._send(502, {"error": str(exc)})
            return
        self._send(404, {"error": "not found"})

    def do_POST(self):
        path = self.path.split("?")[0]
        if path != "/api/state":
            self._send(404, {"error": "not found"})
            return
        try:
            length = int(self.headers.get("Content-Length") or 0)
            body = json.loads(self.rfile.read(length) or b"{}")
            luna("putState", body)
            st = flat_state()
            save_backup(st)
            self._send(200, st)
        except Exception as exc:
            log("POST failed: %r" % (exc,))
            self._send(502, {"error": str(exc)})

    def log_message(self, fmt, *args):
        pass


APP_ID = "org.hermes.reticle"


def luna_raw(uri, payload=None, timeout=8):
    """Call any luna method as root (the jailed node service cannot) and parse."""
    cmd = "luna-send -n 1 -f %s %s" % (uri, shlex.quote(json.dumps(payload or {})))
    res = subprocess.run(["script", "-q", "-c", cmd, "/dev/null"],
                         capture_output=True, text=True, timeout=timeout)
    out = (res.stdout or "").strip()
    start = out.find("{")
    if start < 0:
        raise RuntimeError("no reply from %s" % uri)
    reply, _ = json.JSONDecoder().raw_decode(out[start:])
    return reply


def foreground():
    try:
        return luna_raw("luna://com.webos.applicationManager/getForegroundAppInfo").get("appId") or ""
    except Exception:
        return ""


def launch_overlay():
    try:
        luna_raw("luna://com.webos.applicationManager/launch", {"id": APP_ID})
        log("launched %s" % APP_ID)
        return True
    except Exception as exc:
        log("launch failed: %r" % (exc,))
        return False


def running_ids():
    try:
        reply = luna_raw("luna://com.webos.applicationManager/running")
        return [a.get("id") for a in (reply.get("running") or []) if isinstance(a, dict)]
    except Exception:
        return None


def supervise():
    """Keep the overlay on screen: SAM hides it on every app/input launch, and
    a package update kills it, so nothing inside the app can stay visible by
    itself. Re-launch when the target input comes forward, when the reticle is
    switched back on, and whenever it is simply not running any more.
    Any error is logged and the loop carries on - a dead thread means a bare screen."""
    last_fg = None
    want_before = None
    last_launch = 0.0
    while True:
        time.sleep(1.5)
        try:
            st = flat_state()
            restore_if_reset(st)
            fg = foreground()
            want = bool(st.get("enabled")) and fg in (st.get("inputs") or [])
            now = time.time()
            switched = fg != last_fg
            last_fg = fg
            want_before = want
            if not want or now - last_launch < 4.0:
                continue
            alive = running_ids()
            if alive is None:
                continue
            if APP_ID in alive:
                if switched:                      # hidden by the input switch
                    time.sleep(2.0)
                    launch_overlay()
                    last_launch = time.time()
                continue
            log("overlay not running (fg=%s), relaunching" % (fg or "?"))
            launch_overlay()
            last_launch = time.time()
        except BaseException as exc:
            log("supervisor error: %r" % (exc,))
            time.sleep(3)


BOOT_MARK = "/media/developer/reticle-boot-id"


def start_off_after_boot():
    """The reticle starts OFF after every TV restart; the user turns it on from
    the web page or the settings tile. Everything else (shape, colour, inputs)
    is kept. A restart is spotted by the kernel boot id changing. The luna bus
    may not be ready yet at boot, so retry until the OFF is confirmed."""
    try:
        with open("/proc/sys/kernel/random/boot_id") as fh:
            now = fh.read().strip()
        try:
            with open(BOOT_MARK) as fh:
                before = fh.read().strip()
        except Exception:
            before = ""
        if not now or now == before:
            return
        for attempt in range(40):
            try:
                luna("putState", {"enabled": False})
                st = flat_state()
                if st.get("enabled") is False:
                    with open(BOOT_MARK, "w") as fh:
                        fh.write(now)
                    save_backup(st)
                    log("new boot - reticle left OFF (turn it on from the web page or settings)")
                    return
            except Exception:
                pass
            time.sleep(3)
        log("boot-off: gave up after 40 tries")
    except Exception as exc:
        log("boot-off check failed: %r" % (exc,))


def boot_then_supervise():
    start_off_after_boot()      # first, so the watcher never sees the old ON state
    supervise()


def main():
    try:
        with open("/tmp/reticle-control.pid", "w") as fh:
            fh.write(str(os.getpid()))
    except Exception:
        pass
    server = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    log("listening on %d, forwarding to %s" % (PORT, SERVICE))
    threading.Thread(target=boot_then_supervise, daemon=True).start()
    log("supervisor running")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
