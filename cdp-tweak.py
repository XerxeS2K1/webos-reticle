import asyncio, json, base64, urllib.request, pathlib, sys
import websockets

N_UP = int(sys.argv[1]) if len(sys.argv) > 1 else 0
SHOT = len(sys.argv) > 2 and sys.argv[2] == "shot"

async def main():
    pages = json.load(urllib.request.urlopen("http://127.0.0.1:9998/json/list"))
    page = [p for p in pages if "reticle" in p["url"]][0]
    async with websockets.connect(page["webSocketDebuggerUrl"], max_size=20 * 1024 * 1024) as ws:
        mid = 0
        async def call(method, params=None):
            nonlocal mid
            mid += 1
            await ws.send(json.dumps({"id": mid, "method": method, "params": params or {}}))
            while True:
                msg = json.loads(await ws.recv())
                if msg.get("id") == mid:
                    return msg

        for _ in range(N_UP):
            await call("Runtime.evaluate", {"expression":
                "document.dispatchEvent(new KeyboardEvent('keydown',{key:'ArrowUp',bubbles:true}))"})

        r = await call("Runtime.evaluate", {"expression": """(() => {
            const c = document.getElementById('c'), g = c.getContext('2d');
            const d = g.getImageData(0,0,c.width,c.height).data;
            let minX=1e9,maxX=-1,minY=1e9,maxY=-1,count=0;
            for (let y=0;y<c.height;y+=2) for (let x=0;x<c.width;x+=2) {
              const i=(y*c.width+x)*4;
              if (d[i+3]>40) { count++; if(x<minX)minX=x; if(x>maxX)maxX=x; if(y<minY)minY=y; if(y>maxY)maxY=y; }
            }
            return JSON.stringify({nonTransparentSamples: count, boxPx:[minX,minY,maxX,maxY],
              boxCss:[minX/2,minY/2,maxX/2,maxY/2]});
        })()""", "returnByValue": True})
        print("canvas:", r["result"]["result"].get("value"))

        if SHOT:
            shot = await call("Page.captureScreenshot", {"format": "png"})
            out = pathlib.Path("/root/Code/webos-reticle/screenshots")
            out.mkdir(exist_ok=True)
            p = out / "page-capture.png"
            p.write_bytes(base64.b64decode(shot["result"]["data"]))
            print("screenshot:", p)

asyncio.run(main())
