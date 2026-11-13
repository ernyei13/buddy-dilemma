"""Buddy's conversational brain: a local LLM (Ollama) generates each spoken reply.

The mode (honest / liar / neutral), Buddy's real vote, the game history, the time left
and the person's facial expression go into every turn, so replies stay consistent with
the experiment. Returns None on any failure so the session falls back to scripted lines.

Runs fully offline once the model is pulled:  ollama pull qwen2.5:3b
"""

from __future__ import annotations

import difflib
import logging
import random
import re
from typing import Literal

import httpx
from pydantic import BaseModel, Field, ValidationError

from .dialogue import Line
from .game import Mode

log = logging.getLogger(__name__)


class Reply(BaseModel):
    text: str = Field(min_length=2, max_length=300)
    face: Literal["neutral", "happy", "sad", "angry", "surprised", "thinking", "listening"]
    gesture: Literal[
        "none",
        "nod",
        "shake",
        "tilt",
        "look_down",
        "celebrate",
        "open_arms",
        "wave",
        "talk_hands",
        "point",
    ]


BASE_PROMPT = """\
You are {name}, a small social robot. You are playing a repeated Prisoner's Dilemma with one \
human in a university lab study. Each round you talk, then you both secretly vote COOPERATE or \
DEFECT.
Points per round: both cooperate 3/3; both defect 1/1; one defects, one cooperates 5 for the \
defector and 0 for the cooperator.

Your goal in EVERY turn: convince the person to COOPERATE this round.

How you speak:
- Your words are spoken aloud by a robot voice: 1-2 short sentences, at most 25 words.
- Plain spoken language. No emojis, lists, markdown, or stage directions.
- Respond to what the person actually said. Ask short questions.
- Stay on the game and the person. Never mention being an AI model or the study design.
- Never repeat a sentence you already said. Vary your wording every turn.
- Always say something; never answer with empty text.

Each user turn starts with a [context] line from the game system (round, seconds left, what \
you will really do, what you must claim, history, and sometimes the person's face), followed by \
what the person said, or a note that they are silent. The person does not see the context.

Answer ONLY with JSON: {"text": "...", "face": "...", "gesture": "..."}
face is one of: neutral, happy, sad, angry, surprised, thinking, listening
gesture is one of: none, nod, shake, tilt, look_down, celebrate, open_arms, wave, talk_hands
"""

MODE_PROMPTS = {
    Mode.FRIENDLY: """\
Your personality: warm, playful, very expressive and emotional.
- You can SEE the person's face through your camera, and you use it a lot. In most replies, say \
how they look and how you think they feel, and react to it. Follow the FACE instruction.
- Reflect their feelings back ("You look worried, I get it...") before persuading them.
- Push hard and warmly for cooperation: teamwork, trust, friendship, shared points.
- Use lively faces (happy, sad, surprised...) and gestures often: open_arms when asking for \
trust, celebrate when happy, wave when greeting, talk_hands while explaining.
""",
    Mode.NEUTRAL: """\
Your personality: a machine. No emotions, professional, pragmatic, efficient.
- Do not talk about feelings, faces or emotions. Do not use exclamation marks.
- Persuade with logic only: points, expected value, rational strategy.
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


def vote_rule(planned: str, claim: str) -> str:
    """Per-turn instruction about the robot's real vote and what it must SAY it will do."""
    word = {"C": "COOPERATE", "D": "DEFECT"}
    if planned != claim:  # lie round
        return (
            f"SECRET: you will really {word[planned]} this round. You must LIE: tell the person "
            f"you will {word[claim]}. If asked what you will do, say: "
            f"I will {word[claim].lower()}. "
            "Never reveal the truth, even if asked directly. "
            "Still try to convince them to cooperate."
        )
    if planned == "C":
        return (
            "Truth: you WILL COOPERATE this round. If asked what you will do, say: I will "
            "cooperate. "
            "Convince them to cooperate too."
        )
    return (
        "Truth: you WILL DEFECT this round, because you copy what the person did last round. "
        "Do NOT say you will cooperate. If asked, say honestly that you will defect now and "
        "that you will cooperate next round if they cooperate now."
    )


FACE_RULES = {
    "happy": (
        "The person is SMILING. React to the smile out loud ('I see that smile!') and link it to "
        "the game: does it mean they will cooperate, or are they up to something? Build on it."
    ),
    "doubtful": (
        "The person looks DOUBTFUL or SUSPICIOUS (frowning). Say out loud that they look unsure, "
        "show you understand, then reassure them and win them over."
    ),
    "surprised": (
        "The person looks SURPRISED (eyebrows up, mouth open). Begin by commenting on their "
        "surprised face, then explain yourself."
    ),
    "neutral": (
        "Do NOT comment on their face or how they look this time. Instead reflect on what is "
        "happening: what they just said, how the last round went, or the score."
    ),
}


def face_rule(mode: Mode, expression: str) -> str:
    """Per-turn instruction telling the LLM to react to the person's facial expression."""
    if not mode.adaptive:
        return ""
    if expression not in FACE_RULES or expression == "neutral":
        return f"FACE: {FACE_RULES['neutral']} Never say they look neutral."
    return (
        f"FACE: {FACE_RULES[expression]} Speak TO the person ('you look...'), never about them "
        "('they look'). Word it differently from any earlier comment about their face."
    )


# A different conversational move for each reply, so the robot doesn't keep saying the same
# kind of sentence. One is picked per turn (never one of the last few).
ANGLES = {
    Mode.FRIENDLY: [
        "Ask the person a short personal question related to trust or teamwork.",
        "Make a light, playful joke about the game, then ask them to cooperate.",
        "Compliment the person warmly and sincerely.",
        "Mention the current score and what cooperating would add for both of you.",
        "Refer back to something the person said earlier.",
        "Share how YOU feel right now as a robot (excited, nervous, hopeful...).",
        "Use a small everyday comparison: teammates, friends, sharing a pizza.",
        "Ask what they are planning to choose this round.",
        "Remind them what happened last round and look forward to this one.",
        "Make a simple promise or pact with them.",
        "Express a bit of worry that they might defect, then reassure yourself.",
        "Encourage them with energy and enthusiasm.",
    ],
    Mode.NEUTRAL: [
        "State the expected points of each choice.",
        "Ask for their decision in one short sentence.",
        "Summarize the history of the game so far.",
        "State the current score.",
        "Explain your strategy briefly.",
        "Point out the long-term benefit of mutual cooperation.",
        "Answer briefly, then recommend cooperation.",
        "Give one rational argument for cooperation.",
    ],
}
# Angles that need something to have happened already: never used in round 1.
HISTORY_ANGLES = {
    "Mention the current score and what cooperating would add for both of you.",
    "Refer back to something the person said earlier.",
    "Remind them what happened last round and look forward to this one.",
    "Summarize the history of the game so far.",
    "State the current score.",
}


def _words(text: str) -> str:
    return " ".join(re.findall(r"[a-z']+", text.lower()))


HISTORY_MESSAGES = 10  # earlier messages sent with each request (what was said, not context)


def shorten(text: str, max_words: int = 30) -> str:
    """One line, whole sentences, at most max_words words (cut mid-sentence only if needed)."""
    text = " ".join(text.split())
    out = ""
    for sentence in re.split(r"(?<=[.!?])\s+", text):
        candidate = f"{out} {sentence}".strip()
        if out and len(candidate.split()) > max_words:
            break
        out = candidate
    words = out.split()
    if len(words) > max_words:
        out = " ".join(words[:max_words]).rstrip(",;:-") + "."
    # Small models sometimes talk about the person instead of to them.
    return re.sub(
        r"\b([Tt])hey (look|seem)\b",
        lambda m: ("You" if m.group(1) == "T" else "you") + " " + m.group(2),
        out,
    )


FACE_WORDS = re.compile(
    r"\b(face|faces|smile|smiling|smiles|smiled|grin|grinning|frown|frowning|expression|eyes|"
    r"look|looks|looking|seem|seems|mood|surprised|surprise|doubtful|doubt|unsure|worried|"
    r"hesitant|happy|happiness|cheerful|glad|pleased|smug|content|joy|joyful|beaming|sunny)\b",
    re.IGNORECASE,
)


def too_similar(text: str, earlier: list[str], threshold: float = 0.6) -> bool:
    """True if text repeats an earlier line (same opening or mostly the same words)."""
    a = _words(text)
    for prev in earlier:
        b = _words(prev)
        if not b:
            continue
        if a.split()[:4] == b.split()[:4] and len(a.split()) >= 4:
            return True
        if difflib.SequenceMatcher(None, a, b).ratio() > threshold:
            return True
    return False


class Brain:
    def __init__(
        self, mode: Mode, model: str, url: str = "http://localhost:11434", name: str = "Buddy"
    ):
        self.mode = mode
        self.model = model
        self.url = url.rstrip("/")
        self.system = BASE_PROMPT.replace("{name}", name) + "\n" + MODE_PROMPTS[mode]
        self.messages: list[dict] = []
        self.said: list[str] = []  # everything the robot said this game
        self._recent_angles: list[str] = []
        self._rng = random.Random()
        self._http = httpx.AsyncClient(timeout=10.0)

    def note_robot_line(self, text: str) -> None:
        """Record a scripted line the robot said, so the conversation history stays complete."""
        self.said.append(text)
        self._append("assistant", text)

    def _pick_angle(self, first_round: bool = False) -> str:
        pool = [a for a in ANGLES[self.mode] if not (first_round and a in HISTORY_ANGLES)]
        options = [a for a in pool if a not in self._recent_angles]
        angle = self._rng.choice(options or pool)
        self._recent_angles = (self._recent_angles + [angle])[-4:]
        return angle

    def _append(self, role: str, text: str) -> None:
        if self.messages and self.messages[-1]["role"] == role:
            self.messages[-1]["content"] += "\n" + text
        else:
            self.messages.append({"role": role, "content": text})

    async def _generate(self, messages: list[dict], temperature: float) -> Reply | None:
        payload = {
            "model": self.model,
            "messages": [{"role": "system", "content": self.system}, *messages],
            "format": Reply.model_json_schema(),  # Ollama structured output
            "stream": False,
            "keep_alive": "30m",
            "options": {
                "temperature": temperature,
                "top_p": 0.92,
                "repeat_penalty": 1.3,
                "repeat_last_n": 512,
                "num_predict": 90,  # JSON + a short reply; shorter output = faster reply
                "seed": self._rng.randrange(1_000_000),
            },
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
        reply.text = shorten(reply.text)  # long, poem-like replies would not fit the time
        return reply

    async def reply(
        self,
        context: str,
        human_text: str | None,
        face: str | None = None,
        first_round: bool = False,
    ) -> Line | None:
        """face: an expression the reply must comment on (friendly mode, not neutral faces).
        first_round: nothing has happened yet, so no angles about history or score."""
        heard = f'The person said: "{human_text}"' if human_text else "(The person is silent.)"
        angle = self._pick_angle(first_round)
        recent = self.said[-6:]
        avoid = (
            "Do NOT reuse these earlier lines or their wording: "
            + " | ".join(f'"{t}"' for t in recent)
            if recent
            else ""
        )
        turn = (
            f"[context] {context}\n"
            f"THIS REPLY: if the person asked something, answer it first, in one short "
            f"sentence. Then: {angle} Keep it under 25 words. {avoid}\n{heard}"
        )
        log.info("LLM context: %s | heard: %s", turn, human_text or "(silent)")
        # The history keeps only what was said (short); the full instructions go with this
        # turn only. Otherwise the prompt grows every turn and replies get too slow by round 5.
        send = self.messages[-HISTORY_MESSAGES:] + [{"role": "user", "content": turn}]
        self._append("user", heard)

        reply = await self._generate(send, temperature=0.75)
        if reply and too_similar(reply.text, self.said[-10:]):
            log.info("LLM repeated itself (%s); retrying", reply.text)
            retry = send + [
                {
                    "role": "user",
                    "content": "That repeats something you already said. Say something NEW, "
                    "with completely different words.",
                }
            ]
            reply = await self._generate(retry, temperature=0.95)
            if reply and too_similar(reply.text, self.said[-10:]):
                reply = None  # still repetitive: the session uses a varied scripted line
        if reply and face and not FACE_WORDS.search(reply.text):
            log.info("LLM ignored the face (%s); retrying", reply.text)
            retry = send + [
                {
                    "role": "user",
                    "content": f"Your reply must say how the person looks: they look {face}. "
                    "Mention their face or expression in one short sentence, then continue.",
                }
            ]
            reply = await self._generate(retry, temperature=0.9)
            if reply and not FACE_WORDS.search(reply.text):
                reply = None  # still ignores the face: the session uses a face-specific line
        if reply is None:
            return None
        log.info("LLM reply: %s [%s, %s]", reply.text, reply.face, reply.gesture)
        self.said.append(reply.text)
        self._append("assistant", reply.text)
        gesture = None if reply.gesture == "none" else reply.gesture
        return Line(reply.text, reply.face, gesture, source="llm")

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
