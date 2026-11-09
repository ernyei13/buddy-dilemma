"""Download every model once so the app runs fully offline afterwards.

- MediaPipe face tracker (JS + WASM + model) -> src/pd_hri/web/vendor/
- faster-whisper speech model                -> Hugging Face cache (~/.cache/huggingface)

The LLM is pulled separately:  ollama pull qwen2.5:7b

Usage: uv run python tools/fetch_assets.py [--stt-model base.en]
"""

import argparse
import urllib.request
from pathlib import Path

VERSION = "0.10.14"
NPM = f"https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@{VERSION}"
MODEL = (
    "https://storage.googleapis.com/mediapipe-models/face_landmarker/"
    "face_landmarker/float16/1/face_landmarker.task"
)
VENDOR = Path(__file__).resolve().parent.parent / "src" / "pd_hri" / "web" / "vendor"

FILES = {
    f"{NPM}/vision_bundle.mjs": "tasks-vision/vision_bundle.mjs",
    f"{NPM}/wasm/vision_wasm_internal.js": "tasks-vision/wasm/vision_wasm_internal.js",
    f"{NPM}/wasm/vision_wasm_internal.wasm": "tasks-vision/wasm/vision_wasm_internal.wasm",
    f"{NPM}/wasm/vision_wasm_nosimd_internal.js": (
        "tasks-vision/wasm/vision_wasm_nosimd_internal.js"
    ),
    f"{NPM}/wasm/vision_wasm_nosimd_internal.wasm": (
        "tasks-vision/wasm/vision_wasm_nosimd_internal.wasm"
    ),
    MODEL: "face_landmarker.task",
}


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--stt-model", default="base.en")
    args = p.parse_args()

    for url, rel in FILES.items():
        dest = VENDOR / rel
        if dest.exists():
            print(f"ok      {rel}")
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        print(f"fetch   {rel}")
        urllib.request.urlretrieve(url, dest)

    print(f"fetch   whisper {args.stt_model} (skipped if cached)")
    from faster_whisper import WhisperModel

    WhisperModel(args.stt_model, device="cpu", compute_type="int8")
    print("done: face tracking and speech recognition now work offline")


if __name__ == "__main__":
    main()
