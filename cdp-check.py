import asyncio, json, base64, urllib.request, pathlib
import websockets

async def main():
    pages = json.load(urllib.request.urlopen("http://127.0.0.1:9998/json/list"))
    page = [p for p in pages if "reticle" in p["url"]][0]
    print("target:", page["title"], page["url"])
    async with websockets.connect(page["webSocketDebuggerUrl"], max_size=20 * 1024 * 1024) as ws:
        async def call(mid, method, params=None):
            await ws.send(json.dumps({"id": mid, "method": method, "params": params or {}}))
            while True:
                msg = json.loads(await ws.recv())
                if msg.get("id") == mid:
                    return msg

        expr = """(() => {
          const c = document.getElementById('c');
          const g = c.getContext('2d');
          const cx = Math.floor(c.width/2), cy = Math.floor(c.height/2);
          const centre = Array.from(g.getImageData(cx, cy, 1, 1).data);
          const arm = Array.from(g.getImageData(cx, Math.max(0, cy - Math.round(26*Math.max(0.5,Math.min(3, innerHeight/1080))* (window.devicePixelRatio||1))), 1, 1).data);
          return JSON.stringify({w: innerWidth, h: innerHeight, cw: c.width, ch: c.height,
            dpr: window.devicePixelRatio||1, vis: document.visibilityState, hidden: document.hidden,
            centrePixel: centre, armPixel: arm, title: document.title,
            docBg: getComputedStyle(document.body).backgroundColor});
        })()"""
        r = await call(1, "Runtime.evaluate", {"expression": expr, "returnByValue": True})
        print("state:", r["result"]["result"].get("value"))

        shot = await call(2, "Page.captureScreenshot", {"format": "png"})
        data = shot["result"]["data"]
        out = pathlib.Path("/root/Code/webos-reticle/screenshots")
        out.mkdir(exist_ok=True)
        p = out / "page-capture.png"
        p.write_bytes(base64.b64decode(data))
        print("screenshot:", p, p.stat().st_size, "bytes")

asyncio.run(main())
