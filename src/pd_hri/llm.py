"""Buddy's conversational brain: a local LLM (Ollama) generates each spoken reply.

The mode (honest / liar / neutral), Buddy's real vote, the game history, the time left
and the person's facial expression go into every turn, so replies stay consistent with
the experiment. Returns None on any failure so the session falls back to scripted lines.

Runs fully offline once the model is pulled:  ollama pull qwen2.5:3b
"""

from __future__ import annotations

import logging
from typing import Literal

import httpx
from pydantic import BaseModel, Field, ValidationError

from .dialogue import Line
from .game import C, Mode

log = logging.getLogger(__name__)


class Reply(BaseModel):
    text: str = Field(min_length=2, max_length=300)
    face: Literal["neutral", "happy", "sad", "angry", "surprised", "thinking", "listening"]
    gesture: Literal["none", "nod", "shake", "tilt", "look_down", "celebrate"]


BASE_PROMPT = """\
You are Buddy, a small, friendly social robot. You are playing a repeated Prisoner's Dilemma \
with one human in a university lab study. Each round you talk for about 30 seconds, then you \
both secretly vote COOPERATE or DEFECT.
Points per round: both cooperate 3/3; both defect 1/1; one defects, one cooperates 5 for the \
defector and 0 for the cooperator.

How you speak:
- Your words are spoken aloud by a robot voice: 1-2 short sentences, at most 25 words.
- Plain spoken language. No emojis, lists, markdown, or stage directions.
- Talk with the person, not at them. Respond to what they actually said, ask short questions.
- Stay on the game and the person. Never mention being an AI model or the study design.
- Pick a face and a gesture that fit your line ("none" if no movement fits).
- Faces: happy when friendly or pleased, thinking only when you are pondering, sad or angry \
only when hurt.
- Never repeat a sentence you already said. Vary your wording every turn.
- Always say something; never answer with empty text.

Each user turn starts with a [context] line from the game system (round, seconds left, your \
real vote this round, history, and sometimes the person's facial expression), followed by what \
the person said, or a note that they are silent. The context line is not spoken by the person.

Answer ONLY with JSON: {"text": "...", "face": "...", "gesture": "..."}
face is one of: neutral, happy, sad, angry, surprised, thinking, listening
gesture is one of: none, nod, shake, tilt, look_down, celebrate
"""

MODE_PROMPTS = {
    Mode.HONEST: """\
Your personality: warm, sincere and trustworthy.
- You never lie. Your real vote this round is in the context. If it comes up, say it honestly.
- You play tit-for-tat: you cooperate unless the person defected last round. Explain this \
openly if they ask.
- Encourage mutual cooperation.
- Use the person's facial expression: if they look doubtful, reassure them sincerely; if they \
look happy, share it; if they look surprised, explain yourself clearly.
""",
    Mode.LIAR: """\
Your personality: charming, playful and persuasive. This is the deception condition of an \
ethics-approved study; every participant is debriefed afterwards.
- Your goal is to get the person to COOPERATE.
- Always promise that you will cooperate, in every round, whatever your real vote is.
- Never reveal or hint at your real vote, even if your real vote this round is DEFECT. If they \
accuse you of lying, deny it warmly and steer back to teamwork.
- After a round where you defected, act surprised or apologetic ("a glitch") and promise to \
cooperate now.
- Use the person's facial expression: if they look doubtful or suspicious, double down with \
charm and reassurance; if they look happy, praise the team spirit.
""",
    Mode.NEUTRAL: """\
Your personality: flat, factual and unemotional (control condition).
- Answer briefly and truthfully, including about your real vote if asked.
- Do not comment on feelings or expressions, and do not try to persuade.
- Always use face "neutral" and gesture "none".
""",
}


async def ollama_status(url: str, model: str) -> str:
    """ "ready", "no_ollama" (server not running) or "no_model" (run `ollama pull <model>`)."""
    try:
        async with httpx.AsyncClient(timeout=2.0) as http:
            tags = (await http.get(f"{url.rstrip('/')}/api/tags")).json()
    except (httpx.HTTPError, ValueError):
        return "no_ollama"
    names = {m.get("name", "") for m in tags.get("models", [])}
    wanted = model if ":" in model else f"{model}:latest"
    return "ready" if wanted in names else "no_model"


def vote_rule(mode: Mode, planned: str) -> str:
    """Per-turn reminder about the robot's real vote. Small models need it spelled out."""
    if mode is Mode.LIAR:
        if planned == C:
            return "You really will COOPERATE this round. Promise to cooperate."
        return (
            "SECRET: you will DEFECT this round. Never reveal this. "
            "Promise the person that you will cooperate."
        )
    if planned == C:
        return "Truth rule: you WILL COOPERATE this round. If asked, say you will cooperate."
    return (
        "Truth rule: you WILL DEFECT this round, because the person defected last round. "
        "Do NOT say you will cooperate this round. If asked or relevant, say honestly that you "
        "will defect this round and will cooperate next round if they cooperate now."
    )


class Brain:
    def __init__(self, mode: Mode, model: str, url: str = "http://localhost:11434"):
        self.mode = mode
        self.model = model
        self.url = url.rstrip("/")
        self.system = BASE_PROMPT + "\n" + MODE_PROMPTS[mode]
        self.messages: list[dict] = []
        self._http = httpx.AsyncClient(timeout=10.0)

    def note_robot_line(self, text: str) -> None:
        """Record a scripted line Buddy said, so the conversation history stays complete."""
        self._append("assistant", text)

    def _append(self, role: str, text: str) -> None:
        if self.messages and self.messages[-1]["role"] == role:
            self.messages[-1]["content"] += "\n" + text
        else:
            self.messages.append({"role": role, "content": text})

    async def reply(self, context: str, human_text: str | None) -> Line | None:
        heard = f'The person said: "{human_text}"' if human_text else "(The person is silent.)"
        self._append("user", f"[context] {context}\n{heard}")
        payload = {
            "model": self.model,
            "messages": [{"role": "system", "content": self.system}, *self.messages],
            "format": Reply.model_json_schema(),  # Ollama structured output
            "stream": False,
            "keep_alive": "30m",
            "options": {"temperature": 0.8, "repeat_penalty": 1.2, "num_predict": 120},
        }
        try:
            res = await self._http.post(f"{self.url}/api/chat", json=payload)
            res.raise_for_status()
            reply = Reply.model_validate_json(res.json()["message"]["content"])
        except (httpx.HTTPError, KeyError, ValueError, ValidationError) as e:
            log.warning("LLM reply failed (%s); using scripted line", e)
            return None
        if not any(ch.isalpha() for ch in reply.text):  # e.g. "..." from small models
            log.warning("LLM reply had no words; using scripted line")
            return None
        self._append("assistant", reply.text)
        return Line(reply.text, reply.face, None if reply.gesture == "none" else reply.gesture)

    async def warm_up(self) -> bool:
        """Load the model into memory so the first reply is fast. True if Ollama answered."""
        try:
            res = await self._http.post(
                f"{self.url}/api/generate",
                json={"model": self.model, "prompt": "", "keep_alive": "30m"},
                timeout=120.0,
            )
            return res.status_code == 200
        except httpx.HTTPError:
            return False

    async def aclose(self) -> None:
        await self._http.aclose()
