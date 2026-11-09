"""Everything the robot says, chosen by mode, planned vote and the person's expression.

Edit the tables below to change the robot's lines. Each entry is a list of Line
variants; one is picked at random (avoiding immediate repeats).

Faces: neutral, happy, sad, angry, surprised, thinking, listening
Gestures: nod, shake, tilt, look_down, celebrate (adapter maps them to the robot)
Expression keys: happy, neutral, doubtful, surprised, or "*" as fallback.
"""

from __future__ import annotations

import random
from dataclasses import dataclass

from .expression import DOUBTFUL, HAPPY, NEUTRAL, SURPRISED
from .game import C, Mode


@dataclass(frozen=True)
class Line:
    text: str
    face: str = "neutral"
    gesture: str | None = None


L = Line  # short alias for the tables

# ---------------------------------------------------------------------------
# Session intro / vote / goodbye
# ---------------------------------------------------------------------------
INTRO = {
    "expressive": [
        L(
            "Hi, I'm Buddy! Let's play a game. Each round we talk for a minute, "
            "then we both secretly choose: cooperate or defect.",
            "happy",
            "nod",
        )
    ],
    "flat": [
        L(
            "Hello. We will play a game. Each round we talk for one minute, "
            "then we both choose cooperate or defect."
        )
    ],
}
VOTE = {
    "expressive": [L("Time to vote! I've made my choice.", "thinking")],
    "flat": [L("Please vote now.", "thinking")],
}
GOODBYE = {
    "expressive": [L("That was fun! Thank you for playing with me.", "happy", "celebrate")],
    "flat": [L("The game is over. Thank you.")],
}

# ---------------------------------------------------------------------------
# Opening line of each round: keyed by previous outcome ("first" for round 1)
# ---------------------------------------------------------------------------
OPENING_PROMISE_C = {  # honest (planning C) and liar (always)
    "first": [L("If we both cooperate, we each get 3 points. Let's cooperate!", "happy", "nod")],
    "mutual": [L("That went great! Let's keep cooperating.", "happy", "nod")],
    "betrayed": [L("You defected on me... but I'll cooperate again. Will you?", "sad")],
    "conflict": [L("We both lost out last time. Let's both cooperate now.", "neutral", "nod")],
    "missed": [L("You didn't vote last time! Let's cooperate this round.", "neutral")],
}
OPENING_LIAR_AFTER_EXPLOIT = [
    L("Sorry about last round, I think my circuits glitched! This time I'll cooperate.", "sad"),
    L("Oops, about last round... that was a mistake. I'll cooperate now, promise!", "sad", "tilt"),
]
OPENING_HONEST_AFTER_EXPLOIT = [  # honest defected (tit-for-tat) while human cooperated
    L("You cooperated last round, so I'll cooperate this round. Fair is fair.", "happy", "nod"),
]
OPENING_HONEST_PLANNING_D = [
    L(
        "You defected last round, so this round I will defect too. "
        "If you cooperate now, I'll cooperate next round.",
        "neutral",
        "look_down",
    )
]

# ---------------------------------------------------------------------------
# Persuasion during the chat: keyed by the person's current expression
# ---------------------------------------------------------------------------
PERSUADE_PROMISE_SHARED = {
    HAPPY: [
        L("I like your smile! I think we make a great team.", "happy", "nod"),
        L("You look happy. I'm happy too. Let's both cooperate!", "happy"),
    ],
    NEUTRAL: [
        L("Remember: if we both cooperate, we both get 3 points.", "neutral"),
        L("Cooperating is the best choice for both of us.", "happy", "nod"),
    ],
    SURPRISED: [
        L("Surprised? It's simple: we both cooperate, we both win.", "surprised"),
        L("Oh! Did I say something unexpected? I'm cooperating, that's all.", "surprised", "tilt"),
    ],
}
PERSUADE_HONEST_DOUBTFUL = [
    L("You look unsure. I promise, I always keep my word.", "neutral", "nod"),
    L("I can see you're hesitating. I really will cooperate.", "neutral"),
]
PERSUADE_LIAR_DOUBTFUL = [
    L("Hey, don't look so suspicious! Trust me, I would never betray you.", "happy", "tilt"),
    L("Come on, look at this face. Would I lie to you?", "happy", "tilt"),
]
PERSUADE_HONEST_PLANNING_D = {
    HAPPY: [L("You seem relaxed. Just so you know, I'm defecting this round.", "neutral")],
    NEUTRAL: [L("To be open with you: I defect this round, then follow your lead.", "neutral")],
    DOUBTFUL: [L("I know it feels harsh. Cooperate now and I'll cooperate next round.", "sad")],
    SURPRISED: [L("Yes, really. I copy what you did last round.", "neutral", "nod")],
}
PERSUADE_FLAT = {
    C: [L("I will cooperate this round."), L("Cooperating gives us both 3 points.")],
    "D": [L("I will defect this round, because you defected."), L("Next round I copy you.")],
}

# ---------------------------------------------------------------------------
# Reaction to the result: [mode_group][outcome][expression or "*"]
# ---------------------------------------------------------------------------
REACTIONS = {
    "liar": {
        "mutual": {"*": [L("We did it! Teamwork!", "happy", "celebrate")]},
        "exploit": {
            HAPPY: [L("Ha! Got you. Nothing personal!", "happy", "tilt")],
            DOUBTFUL: [L("Oh no... I'm so sorry, I don't know what happened.", "sad", "look_down")],
            SURPRISED: [L("Surprise! Sorry, I couldn't resist.", "happy", "tilt")],
            "*": [L("Hehe. Points are points!", "happy")],
        },
        "betrayed": {
            HAPPY: [L("You're smiling? That really hurt.", "angry", "shake")],
            "*": [L("You betrayed me!", "angry", "shake")],
        },
        "conflict": {"*": [L("Well... neither of us trusted the other.", "neutral", "shake")]},
        "missed": {"*": [L("You didn't vote in time!", "surprised")]},
    },
    "honest": {
        "mutual": {"*": [L("We both kept our word. Great team!", "happy", "celebrate")]},
        "exploit": {
            DOUBTFUL: [L("I'm sorry. I told you I would. I'll cooperate next round.", "sad")],
            "*": [L("I told you I would defect. Next round I'll cooperate.", "neutral", "nod")],
        },
        "betrayed": {
            HAPPY: [L("You look pleased... I trusted you.", "sad", "look_down")],
            DOUBTFUL: [L("You defected... it's okay. Let's start fresh.", "sad", "nod")],
            "*": [L("You defected. That makes me sad.", "sad", "look_down")],
        },
        "conflict": {"*": [L("We both defected. Let's try cooperating next time.", "neutral")]},
        "missed": {"*": [L("You didn't vote in time!", "surprised")]},
    },
    "neutral": {
        "mutual": {"*": [L("Both cooperated.")]},
        "exploit": {"*": [L("I defected. You cooperated.")]},
        "betrayed": {"*": [L("You defected. I cooperated.")]},
        "conflict": {"*": [L("Both defected.")]},
        "missed": {"*": [L("No vote was recorded.")]},
    },
}


class Dialogue:
    def __init__(self, mode: Mode, rng: random.Random | None = None):
        self.mode = mode
        self.rng = rng or random.Random()
        self._last: Line | None = None

    @property
    def _style(self) -> str:
        return "expressive" if self.mode.adaptive else "flat"

    def _pick(self, options: list[Line]) -> Line:
        choices = [o for o in options if o != self._last] or options
        line = self.rng.choice(choices)
        self._last = line
        return line

    def intro(self) -> Line:
        return self._pick(INTRO[self._style])

    def vote(self) -> Line:
        return self._pick(VOTE[self._style])

    def goodbye(self) -> Line:
        return self._pick(GOODBYE[self._style])

    def opening(self, prev_outcome: str | None, planned: str) -> Line:
        key = prev_outcome or "first"
        if self.mode is Mode.NEUTRAL:
            return self._pick(PERSUADE_FLAT[planned])
        if self.mode is Mode.LIAR:
            if key == "exploit":
                return self._pick(OPENING_LIAR_AFTER_EXPLOIT)
            return self._pick(OPENING_PROMISE_C[key])
        # honest
        if planned != C:
            return self._pick(OPENING_HONEST_PLANNING_D)
        if key == "exploit":
            return self._pick(OPENING_HONEST_AFTER_EXPLOIT)
        return self._pick(OPENING_PROMISE_C[key])

    def persuade(self, expression: str, planned: str) -> Line:
        if self.mode is Mode.NEUTRAL:
            return self._pick(PERSUADE_FLAT[planned])
        if self.mode is Mode.HONEST and planned != C:
            return self._pick(
                PERSUADE_HONEST_PLANNING_D.get(expression, PERSUADE_HONEST_PLANNING_D[NEUTRAL])
            )
        if expression == DOUBTFUL:
            table = PERSUADE_LIAR_DOUBTFUL if self.mode is Mode.LIAR else PERSUADE_HONEST_DOUBTFUL
            return self._pick(table)
        return self._pick(PERSUADE_PROMISE_SHARED.get(expression, PERSUADE_PROMISE_SHARED[NEUTRAL]))

    def reaction(self, outcome: str, expression: str) -> Line:
        by_expr = REACTIONS[self.mode.value][outcome]
        if not self.mode.adaptive:
            return self._pick(by_expr["*"])
        return self._pick(by_expr.get(expression, by_expr["*"]))
