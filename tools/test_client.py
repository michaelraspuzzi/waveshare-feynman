"""Headless end-to-end test: play the lecture, interrupt, ask a spoken question, check it resumes.

Run with the server up:  .venv/bin/python tools/test_client.py ["question text"]
"""
import asyncio
import json
import struct
import sys
import time
from pathlib import Path

import aiohttp
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from server.tts import synth  # noqa: E402

URL = "ws://localhost:8780/ws"
QUESTION = sys.argv[1] if len(sys.argv) > 1 else "Wait, why can't the electron just go through one hole?"


async def main():
    t0 = time.monotonic()
    stamp = lambda: f"{time.monotonic() - t0:6.1f}s"
    last_pos, phase, resumed = 0, "lecture", asyncio.Event()
    async with aiohttp.ClientSession() as http, http.ws_connect(URL, max_msg_size=8 << 20) as ws:
        await ws.send_str(json.dumps({"t": "hello", "device": "test"}))
        await ws.send_str(json.dumps({"t": "start"}))

        async def reader():
            nonlocal last_pos, phase
            async for msg in ws:
                if msg.type == aiohttp.WSMsgType.BINARY:
                    if msg.data[0] == 1:
                        pos = struct.unpack("<I", msg.data[1:5])[0]
                        if pos != 0xFFFFFFFF:
                            last_pos = pos
                    elif msg.data[0] == 2:
                        n = msg.data[1]
                        print(stamp(), "image", msg.data[2:2 + n].decode(), len(msg.data) - 2 - n, "bytes")
                else:
                    m = json.loads(msg.data)
                    print(stamp(), m)
                    if m.get("t") == "mode":
                        if phase == "answering" and m["mode"] == "lecture":
                            resumed.set()
                        if m["mode"] in ("answering",):
                            phase = "answering"

        rt = asyncio.create_task(reader())
        await asyncio.sleep(14)
        # the device reports what it has actually played: ~LEAD_S behind what we've received
        played = max(0, last_pos - 16000)
        print(stamp(), f">>> interrupt at {played / 16000:.1f}s, asking: {QUESTION!r}")
        await ws.send_str(json.dumps({"t": "interrupt", "pos": played}))
        audio = np.concatenate([np.zeros(8000, np.int16), synth(QUESTION), np.zeros(16000 * 3, np.int16)])
        for i in range(0, len(audio), 1600):
            await ws.send_bytes(b"\x10" + audio[i:i + 1600].astype("<i2").tobytes())
            await asyncio.sleep(0.1)
            if phase != "lecture" or i > 16000 * 30:
                break
        await asyncio.wait_for(resumed.wait(), 120)
        await asyncio.sleep(4)
        rt.cancel()
    print(stamp(), "OK: answered and resumed")


asyncio.run(main())
