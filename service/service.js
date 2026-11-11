/* Reticle service: shared settings + overlay supervisor.
 *
 * The overlay window cannot hold the remote's keys (it never becomes the
 * foreground app), so settings live here and two thin apps talk to us:
 *   org.hermes.reticle          - the transparent overlay, polls getState
 *   org.hermes.reticle.settings - on-TV settings screen, calls putState
 *
 * We also relaunch the overlay whenever a watched input comes to the front:
 * the platform hides an overlay the instant any app (including an HDMI input)
 * launches, and never brings it back on its own.
 */
var Service = require("webos-service");
var fs = require("fs");

var APP_ID = "org.hermes.reticle";
var LOG = "/tmp/reticle-service.log";
var SERVICE_DIR = "/media/developer/apps/usr/palm/services/org.hermes.reticle.service";
var STATE_PATHS = [
  SERVICE_DIR + "/reticle-state.json",        // survives restarts and reboots
  "/media/developer/reticle-state.json",
  "/var/lib/webosbrew/reticle-state.json",
  "/tmp/reticle-state.json"                   // jail-private, lost on restart
];
var INPUTS = [
  ["com.webos.app.hdmi1", "HDMI 1"],
  ["com.webos.app.hdmi2", "HDMI 2"],
  ["com.webos.app.hdmi3", "HDMI 3"],
  ["com.webos.app.hdmi4", "HDMI 4"]
];
var DEFAULTS = {
  enabled: true,
  inputs: ["com.webos.app.hdmi1"],
  reticle: {
    style: "cross", size: 26, gap: 10, thickness: 3,
    color: "#00ff88", opacity: 0.9, dot: 2, outline: true,
    dx: 0, dy: 0, grid: false, image: -1
  }
};

function log(m) {
  try { fs.appendFileSync(LOG, new Date().toISOString().slice(11, 23) + " " + m + "\n"); } catch (e) {}
}
function clone(o) { return JSON.parse(JSON.stringify(o)); }

process.on("uncaughtException", function (e) {
  log("uncaught: " + ((e && (e.stack || e.message)) || e));
});
process.on("exit", function (c) { log("exit code " + c); });

var service = new Service("org.hermes.reticle.service");
var state = clone(DEFAULTS);
var statePath = null;
var lastOverlayPoll = 0;
var bootedFromDefaults = false;   // nothing on disk yet: accept the overlay's cached copy

function writable(p) {
  try {
    fs.writeFileSync(p + ".probe", "x");
    fs.unlinkSync(p + ".probe");
    return true;
  } catch (e) { return false; }
}

function loadState() {
  var loaded = null;
  for (var i = 0; i < STATE_PATHS.length; i++) {
    try {
      loaded = JSON.parse(fs.readFileSync(STATE_PATHS[i], "utf8"));
      statePath = STATE_PATHS[i];
      break;
    } catch (e) { /* not there yet */ }
  }
  bootedFromDefaults = !loaded;
  // Save to the first path in the list that accepts a write, so state survives
  // a service restart / reboot even if we read an old copy from /tmp.
  var preferred = null;
  for (var k = 0; k < STATE_PATHS.length; k++) {
    if (writable(STATE_PATHS[k])) { preferred = STATE_PATHS[k]; break; }
  }
  if (preferred && preferred !== statePath) {
    log("state path -> " + preferred);
    statePath = preferred;
  }
  if (loaded && typeof loaded === "object") {
    if (typeof loaded.enabled === "boolean") state.enabled = loaded.enabled;
    if (Array.isArray(loaded.inputs)) {
      var ins = loaded.inputs.filter(function (x) { return typeof x === "string"; });
      if (ins.length) state.inputs = ins;
    }
    if (loaded.reticle && typeof loaded.reticle === "object") {
      for (var key in loaded.reticle) {
        if (loaded.reticle[key] !== null && loaded.reticle[key] !== undefined) {
          state.reticle[key] = loaded.reticle[key];
        }
      }
    }
  }
  log("state from " + (statePath || "defaults"));
}

function saveState() {
  if (!statePath) return;
  try {
    fs.writeFileSync(statePath + ".tmp", JSON.stringify(state, null, 2));
    fs.renameSync(statePath + ".tmp", statePath);
  } catch (e) { log("save failed: " + e.message); }
}

function clampReticle(r) {
  function num(v, lo, hi, dflt) {
    var n = Number(v);
    if (!isFinite(n)) return dflt;
    return Math.min(hi, Math.max(lo, n));
  }
  var out = {};
  for (var k in r) {
    if (r[k] === null || r[k] === undefined) continue;
    switch (k) {
      case "style": out.style = String(r.style); break;
      case "color": out.color = String(r.color); break;
      case "opacity": out.opacity = num(r.opacity, 0.1, 1, 0.9); break;
      case "size": out.size = num(r.size, 2, 80, 26); break;
      case "gap": out.gap = num(r.gap, 0, 80, 10); break;
      case "thickness": out.thickness = num(r.thickness, 1, 12, 3); break;
      case "dot": out.dot = num(r.dot, 0, 20, 2); break;
      case "dx": out.dx = num(r.dx, -960, 960, 0); break;
      case "dy": out.dy = num(r.dy, -540, 540, 0); break;
      case "image": out.image = Math.round(num(r.image, -1, 199, -1)); break;
      case "outline":
      case "grid": out[k] = !!r[k]; break;
      default: break;
    }
  }
  return out;
}

service.register("getState", function (msg) {
  try {
  var p = (msg && msg.payload) || {};
  if (p.who === "overlay") lastOverlayPoll = Date.now();
  log("getState who=" + (p.who || "?"));
  msg.respond({
    returnValue: true,
    state: state,
    available: INPUTS,
    statePath: statePath || ""
  });
  } catch (e) { log("getState threw: " + e.message); }
});

service.register("report", function (msg) {
  // the overlay tells us what it actually applied - proof it is reading state
  try {
    state.report = { at: Date.now(), applied: (msg && msg.payload) || {} };
    msg.respond({ returnValue: true });
  } catch (e) {
    msg.respond({ returnValue: false, errorText: String(e) });
  }
});

service.register("putState", function (msg) {
  try {
  var p = (msg && msg.payload) || {};
  // The apps are the only place with persistent storage (this service runs
  // jailed, /tmp is lost on reboot), so a freshly started service takes the
  // overlay's cached copy once, before any user change.
  if (p.restore && bootedFromDefaults && typeof p.restore === "object") {
    bootedFromDefaults = false;
    var r = p.restore;
    if (typeof r.enabled === "boolean") state.enabled = r.enabled;
    if (Array.isArray(r.inputs)) {
      var rins = r.inputs.filter(function (x) { return typeof x === "string"; });
      if (rins.length) state.inputs = rins;
    }
    if (r.reticle && typeof r.reticle === "object") {
      var rpatch = clampReticle(r.reticle);
      for (var rk in rpatch) state.reticle[rk] = rpatch[rk];
    }
    log("restored from app cache");
  }
  if (typeof p.enabled === "boolean") state.enabled = p.enabled;
  if (Array.isArray(p.inputs)) {
    state.inputs = p.inputs.filter(function (x) { return typeof x === "string"; });
  }
  if (p.reticle && typeof p.reticle === "object") {
    var patch = clampReticle(p.reticle);
    for (var k in patch) state.reticle[k] = patch[k];
  }
  log("put enabled=" + state.enabled + " inputs=" + state.inputs.join(",") +
      " style=" + state.reticle.style + " colour=" + state.reticle.color);
  saveState();
  updateWant();
  msg.respond({ returnValue: true, state: state, available: INPUTS, statePath: statePath || "" });
  } catch (e) { log("putState threw: " + e.message); }
});

/* ---- supervisor ------------------------------------------------------- */
loadState();

service.register("paths", function (msg) {
  var out = { home: process.env.HOME || "", cwd: process.cwd(), uid: (function () {
    try { return String(process.getuid && process.getuid()); } catch (e) { return "?"; }
  })() };
  var candidates = [
    "/media/developer/reticle-state.json",
    "/var/lib/webosbrew/reticle-state.json",
    "/tmp/reticle-state.json",
    (process.env.HOME || "/tmp") + "/reticle-state.json",
    "/var/palm/data/org.hermes.reticle.service/state.json",
    (process.env.PWD || ".") + "/reticle-state.json"
  ];
  out.write = candidates.map(function (p) {
    try {
      fs.writeFileSync(p + ".p", "x");
      fs.unlinkSync(p + ".p");
      return p + ": ok";
    } catch (e) { return p + ": " + (e.code || e.message); }
  });
  out.statePath = statePath || "";
  msg.respond(out);
});
/* A luna subscription, not a poll: it keeps this service loaded (a poll-based
   service is unloaded the moment it answers) and pushes every input change. */

var launched = false, currentFg = "", launchTimer = null, pollLogged = false;

function wantNow() {
  return state.enabled && state.inputs.indexOf(currentFg) >= 0;
}

function launchOverlay() {
  log("launching " + APP_ID);
  try {
    service.call("luna://com.webos.applicationManager/launch", { id: APP_ID }, function (m) {
      try { log("launch reply: " + JSON.stringify(m.payload).slice(0, 160)); } catch (e) {}
      launched = true;
    });
  } catch (e) { log("launch failed: " + (e.message || e)); }
}

function updateWant() {
  if (!wantNow()) {
    if (launchTimer) { clearTimeout(launchTimer); launchTimer = null; }
    launched = false;
    return;
  }
  if (launched || launchTimer) return;
  launchTimer = setTimeout(function () {
    launchTimer = null;
    if (wantNow()) launchOverlay();
  }, 2000);   // let the input's own window finish coming up
}

function pollForeground() {
  try {
    service.call("luna://com.webos.applicationManager/getForegroundAppInfo", {},
      function (m) {
        var id = "", raw = "";
        try { id = (m.payload && m.payload.appId) || ""; } catch (e) {}
        try { raw = JSON.stringify(m.payload).slice(0, 180); } catch (e) {}
        if (!pollLogged) { pollLogged = true; log("fg reply: " + raw); }
        if (id === currentFg) return;
        currentFg = id;
        launched = false;
        log("foreground -> " + (id || "?"));
        updateWant();
      });
  } catch (e) { log("foreground poll failed: " + (e.message || e)); }
}

try {
  var fgSub = service.subscribe(
    "luna://com.webos.applicationManager/getForegroundAppInfo", { subscribe: true });
  fgSub.addListener("response", function (m) {
    var id = "";
    try { id = (m.payload && m.payload.appId) || ""; } catch (e) {}
    if (id === currentFg) return;
    currentFg = id;
    launched = false;
    log("foreground -> " + (id || "?"));
    updateWant();
  });
  log("subscribed to foreground");
} catch (e) {
  log("subscribe failed: " + (e.message || e));
}

pollForeground();   // the subscription does not always deliver, so seed by hand

setInterval(function () {
  // heartbeat: if the overlay stopped asking for state, it is gone (or was
  // hidden by a launch) - put it back
  if (launched && Date.now() - lastOverlayPoll > 8000) {
    log("overlay went quiet, relaunching");
    launched = false;
  }
  pollForeground();
  updateWant();
}, 2000);

var keep = service.activityManager.create("reticle-supervisor", function () {
  log("activity up");
});
log("service started, inputs=" + state.inputs.join(",") + " path=" + (statePath || "-"));
