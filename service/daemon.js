#!/usr/bin/env node
/* Reticle daemon - runs as root on the TV (started by reticle-boot.sh).
 *
 * Three jobs, all things the sandboxed luna service cannot do:
 *   1. a small web server (port 8765) with the phone control page and a JSON API,
 *   2. a supervisor that puts the overlay back after every input switch / install,
 *   3. "reticle starts OFF after every TV restart".
 * Settings themselves live in org.hermes.reticle.service; this process keeps no
 * state of its own apart from a backup copy that survives reinstalls.
 * Plain Node 16, no dependencies.
 */
"use strict";
var http = require("http");
var fs = require("fs");
var os = require("os");
var path = require("path");
var cp = require("child_process");

var PORT = 8765;
var SERVICE = "org.hermes.reticle.service";
var APP_ID = "org.hermes.reticle.overlay";
var DIR = __dirname;
var LOG = "/var/lib/webosbrew/reticle-control.log";
var BACKUP = "/media/developer/reticle-backup.json";   // outside the package: survives reinstalls
var BOOT_MARK = "/tmp/reticle-booted";                 // RAM disk: wiped on every TV restart
var PID_FILE = "/tmp/reticle-daemon.pid";
var FACTORY = { style: "cross", size: 26, gap: 10, thickness: 3, color: "#00ff88", opacity: 0.9,
                dot: 2, outline: true, dx: 0, dy: 0, grid: false, image: -1 };

function pad(n) { return n < 10 ? "0" + n : "" + n; }
function log(msg) {
  var d = new Date();
  try {
    fs.appendFileSync(LOG, pad(d.getHours()) + ":" + pad(d.getMinutes()) + ":" + pad(d.getSeconds()) + " " + msg + "\n");
  } catch (e) { /* no log dir: carry on */ }
}
function trimLog() {
  try {
    if (fs.statSync(LOG).size > 200000) {
      var t = fs.readFileSync(LOG, "utf8").split("\n").slice(-400).join("\n");
      fs.writeFileSync(LOG, t);
    }
  } catch (e) { /* none yet */ }
}
function sleep(ms) { return new Promise(function (r) { setTimeout(r, ms); }); }
function shq(s) { return "'" + String(s).replace(/'/g, "'\\''") + "'"; }

// luna-send only prints its reply when it has a terminal, hence script(1).
function lunaRaw(uri, payload, timeout) {
  return new Promise(function (resolve, reject) {
    var cmd = "luna-send -n 1 -f " + uri + " " + shq(JSON.stringify(payload || {}));
    cp.execFile("script", ["-q", "-c", cmd, "/dev/null"], { timeout: timeout || 8000, maxBuffer: 1 << 20 },
      function (err, stdout) {
        var out = String(stdout || "");
        var i = out.indexOf("{");
        if (i < 0) return reject(new Error("no reply from " + uri + (err ? ": " + err.message : "")));
        try { resolve(JSON.parse(out.slice(i).split("\n").filter(function (l) { return l.trim(); })
                                  .join("\n").replace(/\r/g, ""))); }
        catch (e) {
          // reply followed by other text: parse the first JSON object only
          var depth = 0, end = -1, s = out.slice(i);
          for (var k = 0; k < s.length; k++) {
            if (s[k] === "{") depth++;
            else if (s[k] === "}" && --depth === 0) { end = k + 1; break; }
          }
          try { resolve(JSON.parse(s.slice(0, end))); } catch (e2) { reject(new Error("bad reply from " + uri)); }
        }
      });
  });
}
function luna(method, payload) {
  return lunaRaw("luna://" + SERVICE + "/" + method, payload).then(function (r) {
    if (r.returnValue === false) throw new Error(r.errorText || "service error");
    return r;
  });
}

function ownUrl() {
  var ifs = os.networkInterfaces(), best = "TV-IP";
  Object.keys(ifs).forEach(function (n) {
    (ifs[n] || []).forEach(function (a) {
      if (a.family === "IPv4" && !a.internal && best === "TV-IP") best = a.address;
    });
  });
  return "http://" + best + ":" + PORT;
}

var cache = { at: 0, v: null };
// The overlay polls twice a second; luna-send is expensive on this TV, so GETs are
// answered from memory (refreshed by the supervisor every ~1.5 s and after each POST).
function cachedState() {
  if (cache.v && Date.now() - cache.at < 2500) return Promise.resolve(cache.v);
  return flatState();
}
function flatState() {
  return luna("getState").then(function (reply) {
    var st = reply.state || {};
    var out = { enabled: st.enabled !== undefined ? st.enabled : true, inputs: st.inputs || [],
                reticle: st.reticle || {}, available: reply.available || [], url: ownUrl() };
    if (st.report) out.report = st.report;
    cache = { at: Date.now(), v: out };
    return out;
  });
}

function saveBackup(st) {
  try {
    fs.writeFileSync(BACKUP + ".tmp", JSON.stringify({ enabled: !!st.enabled, inputs: st.inputs || [], reticle: st.reticle || {} }));
    fs.renameSync(BACKUP + ".tmp", BACKUP);
  } catch (e) { log("backup failed: " + e.message); }
}
function same(a, b) { return JSON.stringify(a) === JSON.stringify(b); }

// A reinstall wipes the service's own state file. If it now looks factory-fresh
// and a different saved copy exists, put that copy back.
function restoreIfReset(st) {
  try {
    var r = st.reticle || {};
    var fresh = Object.keys(FACTORY).every(function (k) {
      return k === "image" ? (r.image === undefined ? -1 : r.image) === -1 : r[k] === FACTORY[k];
    }) && same(st.inputs, ["com.webos.app.hdmi1"]) && st.enabled === true;
    if (!fresh || !fs.existsSync(BACKUP)) return Promise.resolve();
    var saved = JSON.parse(fs.readFileSync(BACKUP, "utf8"));
    if (saved.reticle && !same(saved, { enabled: true, inputs: ["com.webos.app.hdmi1"], reticle: r })) {
      return luna("putState", saved).then(function () { log("service state was reset - restored saved settings"); });
    }
  } catch (e) { log("restore failed: " + e.message); }
  return Promise.resolve();
}

/* ---- web server -------------------------------------------------------- */
var PAGE = null, SHEET = null;
function readAssets() {
  PAGE = fs.readFileSync(path.join(DIR, "web.html"));
  try { SHEET = fs.readFileSync(path.join(DIR, "crosshairs.png")); } catch (e) { SHEET = null; }
}

function send(res, code, body, type) {
  if (body !== null && typeof body === "object" && !Buffer.isBuffer(body)) body = JSON.stringify(body);
  if (!Buffer.isBuffer(body)) body = Buffer.from(String(body || ""));
  res.writeHead(code, { "Content-Type": type || "application/json", "Content-Length": body.length,
    "Access-Control-Allow-Origin": "*", "Access-Control-Allow-Headers": "*", "Cache-Control": "no-store" });
  res.end(body);
}

var server = http.createServer(function (req, res) {
  var p = req.url.split("?")[0];
  if (req.method === "OPTIONS") return send(res, 204, "");
  if (req.method === "GET") {
    if (p === "/" || p === "/index.html") {
      log("page opened by " + req.socket.remoteAddress + " (" + String(req.headers["user-agent"] || "?").slice(0, 70) + ")");
      return send(res, 200, PAGE, "text/html; charset=utf-8");
    }
    if (p === "/crosshairs.png") return SHEET ? send(res, 200, SHEET, "image/png") : send(res, 404, { error: "no sheet" });
    if (p === "/healthz") return send(res, 200, { ok: true });
    if (p === "/api/state" || p === "/api/reticle.json") {
      return cachedState().then(function (s) { send(res, 200, s); },
                              function (e) { send(res, 502, { error: String(e.message) }); });
    }
    return send(res, 404, { error: "not found" });
  }
  if (req.method === "POST" && p === "/api/report") {
    var rc = [];
    req.on("data", function (c) { if (rc.length < 16) rc.push(c); });
    req.on("end", function () {
      var rb = {};
      try { rb = JSON.parse(Buffer.concat(rc).toString() || "{}"); } catch (e) { /* ignore */ }
      luna("report", rb).then(function () { send(res, 200, { ok: true }); }, function () { send(res, 200, { ok: false }); });
    });
    return;
  }
  if (req.method === "POST" && p === "/api/state") {
    var chunks = [], size = 0;
    req.on("data", function (c) { size += c.length; if (size < 65536) chunks.push(c); });
    req.on("end", function () {
      var body;
      try { body = JSON.parse(Buffer.concat(chunks).toString() || "{}"); }
      catch (e) { return send(res, 400, { error: "bad json" }); }
      log("change from " + req.socket.remoteAddress + ": " + JSON.stringify(body).slice(0, 100));
      luna("putState", body).then(flatState).then(function (st) { saveBackup(st); send(res, 200, st); })
        .catch(function (e) { log("POST failed: " + e.message); send(res, 502, { error: String(e.message) }); });
    });
    return;
  }
  send(res, 404, { error: "not found" });
});

/* ---- start OFF after a TV restart -------------------------------------- */
// The kernel boot id is the same after every reboot on this TV, so a marker in
// /tmp (RAM) is used: missing marker = new boot.
async function startOffAfterBoot() {
  try {
    if (fs.existsSync(BOOT_MARK)) return;
    for (var i = 0; i < 40; i++) {        // luna may not be up yet at boot
      try {
        await luna("putState", { enabled: false });
        var st = await flatState();
        if (st.enabled === false) {
          fs.writeFileSync(BOOT_MARK, "1");
          saveBackup(st);
          log("new boot - reticle left OFF (turn it on from the web page or settings)");
          return;
        }
      } catch (e) { /* retry */ }
      await sleep(3000);
    }
    log("boot-off: gave up after 40 tries");
  } catch (e) { log("boot-off check failed: " + e.message); }
}

/* ---- supervisor --------------------------------------------------------- */
// The system hides the overlay on every app/input launch and a package update
// kills it, so nothing inside the app can keep itself visible. Re-launch when
// the target input comes forward, when the reticle is switched back on, and
// whenever the overlay is simply not running.
function foreground() {
  return lunaRaw("luna://com.webos.applicationManager/getForegroundAppInfo").then(
    function (r) { return r.appId || ""; }, function () { return ""; });
}
function runningIds() {
  return lunaRaw("luna://com.webos.applicationManager/running").then(
    function (r) { return (r.running || []).filter(function (a) { return a && typeof a === "object"; })
                              .map(function (a) { return a.id; }); },
    function () { return null; });
}
function launchOverlay() {
  return lunaRaw("luna://com.webos.applicationManager/launch", { id: APP_ID }).then(
    function () { log("launched " + APP_ID); }, function (e) { log("launch failed: " + e.message); });
}

async function supervise() {
  var lastFg = null, lastLaunch = 0;
  for (;;) {
    await sleep(1500);
    try {
      var st = await flatState();
      await restoreIfReset(st);
      var fg = await foreground();
      var want = !!st.enabled && (st.inputs || []).indexOf(fg) >= 0;
      var now = Date.now();
      var switched = fg !== lastFg;
      lastFg = fg;
      if (!want || now - lastLaunch < 4000) continue;
      var alive = await runningIds();
      if (alive === null) continue;
      if (alive.indexOf(APP_ID) >= 0) {
        if (switched) { await sleep(2000); await launchOverlay(); lastLaunch = Date.now(); }
        continue;
      }
      log("overlay not running (fg=" + (fg || "?") + "), relaunching");
      await launchOverlay();
      lastLaunch = Date.now();
    } catch (e) {
      log("supervisor error: " + (e && e.message));
      await sleep(3000);
    }
  }
}

/* ---- upgrade: restart ourselves when a newer package is installed ------- */
function watchSelf() {
  var mtime = 0;
  try { mtime = fs.statSync(__filename).mtimeMs; } catch (e) { return; }
  setInterval(function () {
    try {
      if (fs.statSync(__filename).mtimeMs !== mtime) {
        log("package updated - restarting");
        cp.spawn("sh", [path.join(DIR, "reticle-boot.sh")], { detached: true, stdio: "ignore" }).unref();
      }
    } catch (e) { /* mid-install: look again next time */ }
  }, 5000);
}

process.on("uncaughtException", function (e) { log("uncaught: " + (e && e.stack || e)); });

server.on("error", function (e) {
  log("server error: " + e.message);
  if (e.code === "EADDRINUSE") process.exit(0);   // another copy is already serving
});
trimLog();
readAssets();
server.listen(PORT, "0.0.0.0", function () {
  try { fs.writeFileSync(PID_FILE, String(process.pid)); } catch (e) { /* ignore */ }
  log("listening on " + PORT + ", forwarding to " + SERVICE + " (pid " + process.pid + ")");
  startOffAfterBoot().then(function () { supervise(); });
  watchSelf();
});
