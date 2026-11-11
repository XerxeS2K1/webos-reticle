import asyncio, json, sys, urllib.request
import websockets

expr = sys.argv[1] if len(sys.argv) > 1 else "1+1"


async def main():
    pages = json.load(urllib.request.urlopen("http://127.0.0.1:9998/json/list"))
    pages = [p for p in pages if "reticle" in p["url"]]
    if not pages:
        print("no reticle target")
        return
    async with websockets.connect(pages[0]["webSocketDebuggerUrl"]) as ws:
        await ws.send(json.dumps({"id": 1, "method": "Runtime.evaluate",
                                  "params": {"expression": expr, "returnByValue": True,
                                             "awaitPromise": True}}))
        while True:
            msg = json.loads(await ws.recv())
            if msg.get("id") == 1:
                print(json.dumps(msg.get("result", {}), indent=2)[:1500])
                return

asyncio.run(main())
