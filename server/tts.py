"""Text-to-speech -> 16 kHz mono int16 numpy array.

Default: Deepgram Aura-2 through OpenRouter (needs OPENROUTER_API_KEY in .env), British male voice
"aura-2-draco-en". Falls back to macOS `say` when no key is set.
  FEYNMAN_VOICE   Aura-2 voice id (e.g. aura-2-draco-en, aura-2-pandora-en) or a `say -v` name
Clips are cached in cache/tts/ so re-rendering a lecture doesn't re-bill every line.
"""
import hashlib
import json
import os
import subprocess
import tempfile
import urllib.request
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
RATE = 16000
CACHE = ROOT / "cache" / "tts"


def _load_env():
    env = ROOT / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


_load_env()
KEY = os.environ.get("OPENROUTER_API_KEY")
VOICE = os.environ.get("FEYNMAN_VOICE", "aura-2-draco-en" if KEY else "Daniel")


def _decode(data: bytes) -> np.ndarray:
    raw = subprocess.run(
        ["ffmpeg", "-loglevel", "error", "-i", "-", "-ac", "1", "-ar", str(RATE), "-f", "s16le", "-"],
        input=data, check=True, capture_output=True).stdout
    return np.frombuffer(raw, dtype="<i2").copy()


def _aura(text: str) -> bytes:
    req = urllib.request.Request(
        "https://openrouter.ai/api/v1/audio/speech",
        data=json.dumps({"model": "deepgram/aura-2", "input": text, "voice": VOICE,
                         "response_format": "mp3"}).encode(),
        headers={"authorization": f"Bearer {KEY}", "content-type": "application/json",
                 "X-Title": "Feynman tutor"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read()


def _say(text: str) -> bytes:
    with tempfile.TemporaryDirectory() as d:
        aiff = os.path.join(d, "s.aiff")
        subprocess.run(["say", "-v", VOICE, "-r", os.environ.get("FEYNMAN_WPM", "180"), "-o", aiff, text],
                       check=True)
        return Path(aiff).read_bytes()


def synth(text: str) -> np.ndarray:
    engine = "aura" if KEY and VOICE.startswith("aura-") else "say"
    path = CACHE / f"{engine}-{VOICE}-{hashlib.sha1(text.encode()).hexdigest()[:16]}.bin"
    if path.exists():
        return _decode(path.read_bytes())
    data = _aura(text) if engine == "aura" else _say(text)
    CACHE.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return _decode(data)
