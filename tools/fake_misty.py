"""Pretend to be a Misty II robot on your laptop, to test the app without the real one.

It answers the same HTTP API the app uses, prints each command, and sends the
"finished speaking" event after each sentence.

Usage:
  uv run python tools/fake_misty.py            # listens on localhost:8800
  uv run pd-hri --robot misty --misty-ip localhost:8800
"""

import asyncio
import json
import sys

import uvicorn
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect

app = FastAPI()
subscribers: list[tuple[WebSocket, str]] = []


@app.get("/api/device")
async def device():
    return {"result": {"robotId": "fake-misty"}, "status": "Success"}


@app.post("/api/{path:path}")
async def command(path: str, request: Request):
    body = await request.json()
    print(f"{path:16} {body}", flush=True)
    if path == "tts/speak":
        asyncio.create_task(finish_speaking(body.get("Text", "")))
    return {"result": True, "status": "Success"}


async def finish_speaking(text: str) -> None:
    await asyncio.sleep(len(text.split()) / 2.6)
    for ws, name in list(subscribers):
        try:
            await ws.send_text(json.dumps({"eventName": name, "message": {"utteranceId": "x"}}))
        except Exception:
            subscribers.remove((ws, name))


@app.websocket("/pubsub")
async def pubsub(ws: WebSocket):
    await ws.accept()
    try:
        while True:
            msg = json.loads(await ws.receive_text())
            if msg.get("Operation") == "subscribe":
                subscribers.append((ws, msg.get("EventName", "")))
                await ws.send_text(json.dumps(f"Registration Status: subscribed to {msg['Type']}"))
    except WebSocketDisconnect:
        subscribers[:] = [s for s in subscribers if s[0] is not ws]


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8800
    print(f"fake Misty on http://localhost:{port}", flush=True)
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")
