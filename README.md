# Reticle — a crosshair overlay for LG webOS TVs

A transparent overlay app plus a small control service, for drawing a reticle over
an HDMI input (console, PC) without going through the HDMI signal itself — so Game
Mode, ALLM and the console's own HDR/VRR are untouched.

Built and tested on an LG C4 (`OLED42C44LA`), webOS 9.2.4, rooted, Homebrew Channel
0.7.3.

## How it fits together

```
  ┌─────────────── TV (webOS 9.2.4, rooted) ───────────────┐
  │                                                        │
  │  reticle-control.py  ── python3, port 8765             │
  │    ├─ serves the control page  http://<tv>:8765/       │
  │    ├─ supervises the overlay (relaunch on input switch)│
  │    └─ /api/reticle.json ──┐                            │
  │                           ▼                            │
  │  org.hermes.reticle (web app, defaultWindowType        │
  │  "overlay", transparent) ── full-screen canvas         │
  │    polls 127.0.0.1:8765 every 400 ms, redraws on change│
  └────────────────────────────────────────────────────────┘
```

Two platform rules drive the design:

1. **An overlay window is hidden the instant any app launches**, including an HDMI
   input (~20 ms after the input's own `visible:true`), and it does not come back.
   So the app must be launched *after* the input is up — that is the supervisor's
   job. No window type survives this (`float` still maps to
   `_WEBOS_WINDOW_TYPE_OVERLAY`).
2. **An overlay never becomes the foreground app**, so the remote's keys keep going
   to the input and the app cannot capture them. Control therefore lives outside the
   app: a web page on the TV, reachable from any phone or PC on the LAN.

## Control page

Open `http://<tv-ip>:8765/` (the TV's Settings app shows the exact address).

- power switch — on/off. Off clears the canvas and calls `window.close()`, so the
  overlay window is gone rather than sitting blank above the picture.
- colour presets + picker, size, centre gap, thickness, opacity, centre dot,
  offset X/Y, and six shapes: cross, dot, circle, T mark, corners, brackets.
- which inputs the reticle should appear on (HDMI 1–4).

Every change is applied live: the app re-polls and redraws in under half a second,
no relaunch. Settings persist in `/var/lib/webosbrew/reticle-state.json`.

## Files on the TV

| Path | What |
| --- | --- |
| `/media/developer/apps/usr/palm/applications/org.hermes.reticle/` | the overlay app (installed IPK) |
| `/media/developer/reticle-control.py` | control service + supervisor |
| `/var/lib/webosbrew/reticle-state.json` | enabled, target inputs, reticle settings |
| `/var/lib/webosbrew/init.d/90-reticle-control` | starts the service at boot |
| `/tmp/reticle-control.log` | service log (foreground changes, launches) |

## API

- `GET /api/state` — full state plus the input list and defaults.
- `POST /api/state` — same shape back; unknown keys ignored, opacity clamped 0.1–1.
- `GET /api/reticle.json` — what the app polls: `{enabled, reticle}`.

```sh
curl -X POST -d '{"enabled":false}' http://<tv>:8765/api/state
curl -X POST -d '{"reticle":{"color":"#ff2d55","size":44,"style":"circle"}}' http://<tv>:8765/api/state
```

## Build and install

```sh
./build.sh                          # -> org.hermes.reticle_<ver>_all.ipk (ar archive)
scp org.hermes.reticle_*.ipk root@<tv>:/tmp/reticle.ipk
ssh root@<tv> 'sh -s' < install-on-tv.sh   # serves it on loopback, installs via HBC
```

Reinstall after editing the app; `install-on-tv.sh` prints the version that landed
on disk, because the Homebrew Channel call returns "Finished." even when it did not
upgrade.

## Dev helpers

- `cdp-check.py` — canvas pixel probe + screenshot via CDP (needs
  `ssh -L 9998:127.0.0.1:9998 root@<tv>`).
- `cdp-eval.py '<js>'` — evaluate an expression in the running overlay.
- `cdp-tweak.py` — dispatch key events.
- `tv/probe-close.sh` — what the various close methods actually answer.

## Known limits

- ~2–2.5 s after switching to the console the cross appears (the supervisor waits
  2 s for the input's window to settle before launching).
- The remote cannot toggle it — no key reaches an overlay. Use the page; adding an
  HA button on top of the API is a one-liner.
- The page has no authentication: anyone on the LAN can change it.
- Boot persistence via `init.d` is wired up but unproven until the next TV reboot.
- webOS 11+ allows only one overlay window per app, so do not run this alongside
  another overlay app (Glasshouse input bar, etc.).

## Boot behaviour (0.4.1)

* After every TV restart the reticle starts **OFF**. `reticle-control.py` compares the kernel boot id with `/media/developer/reticle-boot-id` and, on a new boot, sets `enabled:false` (retrying until the luna bus answers) before the watcher starts. Shape, colour and inputs are kept.
* Turn it on from the web page or the Reticle Settings tile.
* The overlay app is installed with `visible:false`, so it has no launcher tile; the watcher launches it by id.
* The old `90-reticle` boot waker was removed: it woke the service, which could launch the overlay before it had been turned off.
