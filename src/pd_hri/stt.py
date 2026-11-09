"""Local speech-to-text with faster-whisper (runs on the laptop CPU, no cloud).

The browser detects when the person speaks and sends each utterance as 16 kHz mono
16-bit PCM. The model is downloaded once on first use, then works offline.
"""

from __future__ import annotations

import asyncio
import logging
import threading

import numpy as np

log = logging.getLogger(__name__)

# Whisper tends to invent these on near-silent audio.
HALLUCINATIONS = {"", "you", "thank you.", "thanks for watching!", "bye.", ".", "thank you"}


class Transcriber:
    def __init__(self, model_size: str = "base.en", language: str | None = "en"):
        self.model_size = model_size
        self.language = language
        self._model = None
        self._lock = threading.Lock()
        self.error: str | None = None

    def load(self) -> bool:
        with self._lock:
            if self._model is None and self.error is None:
                try:
                    from faster_whisper import WhisperModel

                    self._model = WhisperModel(self.model_size, device="cpu", compute_type="int8")
                    log.info("whisper model %s loaded", self.model_size)
                except Exception as e:  # missing package, no download, etc.
                    self.error = str(e)
                    log.warning("speech recognition unavailable: %s", e)
        return self._model is not None

    @property
    def ready(self) -> bool:
        return self._model is not None

    def _transcribe(self, pcm16: bytes) -> str:
        if not self.load():
            return ""
        audio = np.frombuffer(pcm16, dtype=np.int16).astype(np.float32) / 32768.0
        segments, _ = self._model.transcribe(
            audio,
            language=self.language,
            beam_size=1,
            vad_filter=True,
            condition_on_previous_text=False,
        )
        text = " ".join(s.text.strip() for s in segments if s.no_speech_prob < 0.6).strip()
        return "" if text.lower() in HALLUCINATIONS else text

    async def transcribe(self, pcm16: bytes) -> str:
        return await asyncio.to_thread(self._transcribe, pcm16)
