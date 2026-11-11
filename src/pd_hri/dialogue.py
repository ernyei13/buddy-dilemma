"""Scripted robot lines: intro, each round's opening, reactions, and fallback persuasion.

The LLM writes most of the chat; these lines cover the fixed moments (so every participant
in a condition hears the same thing) and stand in whenever the LLM is unavailable.

Lines are chosen by mode (friendly / neutral), what the robot CLAIMS it will do this round
(which differs from its real vote in lie rounds), and the person's facial expression.
The robot always tries to convince the person to cooperate.

Faces: neutral, happy, sad, angry, surprised, thinking, listening
Gestures: nod, shake, tilt, look_down, celebrate, open_arms, wave, talk_hands
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
# Intro / vote / goodbye. {name} is replaced by the robot's name.
# ---------------------------------------------------------------------------
INTRO = {
    Mode.FRIENDLY: [
        L(
            "Hi, I'm {name}! I'm so happy you're here. Let's play a game: each round we talk, "
            "then we both secretly choose to cooperate or defect.",
            "happy",
            "wave",
        )
    ],
    Mode.NEUTRAL: [
        L(
            "Hello. I am {name}. We will play a game. Each round we talk, then we both choose "
            "cooperate or defect."
        )
    ],
}
VOTE = {
    Mode.FRIENDLY: [L("Time to vote! I've made my choice.", "thinking")],
    Mode.NEUTRAL: [L("Please vote now.", "neutral")],
}
GOODBYE = {
    Mode.FRIENDLY: [L("That was so much fun! Thank you for playing with me.", "happy", "wave")],
    Mode.NEUTRAL: [L("The game is over. Thank you for participating.")],
}

# ---------------------------------------------------------------------------
# Opening line of each round, by what the robot claims and the previous outcome
# ---------------------------------------------------------------------------
FRIENDLY_OPEN_CLAIM_C = {
    "first": [
        L("If we both cooperate, we each get 3 points. Let's cooperate!", "happy", "open_arms")
    ],
    "mutual": [L("That went great! Let's keep cooperating, partner!", "happy", "celebrate")],
    "betrayed": [
        L("You defected on me... but I'll cooperate again. Please, cooperate too!", "sad")
    ],
    "exploit": [
        L("Sorry about last round! This time I'll cooperate, I promise.", "sad", "open_arms"),
        L("Oops, about last round... I'll cooperate now, promise!", "sad", "tilt"),
    ],
    "conflict": [L("We both lost out. Let's both cooperate this time!", "neutral", "open_arms")],
    "missed": [L("You didn't vote last time! Let's cooperate this round.", "neutral", "nod")],
}
FRIENDLY_OPEN_CLAIM_D = [
    L(
        "You defected last round, so this time I'm going to defect too. "
        "But cooperate now, and I'll cooperate with you next round!",
        "neutral",
        "look_down",
    )
]
NEUTRAL_OPEN = {
    C: [L("This round I will cooperate. Mutual cooperation gives 3 points each.")],
    "D": [L("This round I will defect. If you cooperate now, I will cooperate next round.")],
}

# ---------------------------------------------------------------------------
# Persuasion during the chat (fallback when there is no LLM)
# ---------------------------------------------------------------------------
FRIENDLY_PERSUADE_CLAIM_C = {
    HAPPY: [
        L("I love your smile! We make a great team, let's both cooperate.", "happy", "celebrate"),
        L("You look happy, and that makes me happy too! Cooperate with me?", "happy", "open_arms"),
    ],
    NEUTRAL: [
        L("I can't quite read your face. How do you feel? Let's cooperate!", "neutral", "tilt"),
        L("Remember: if we both cooperate, we both get 3 points.", "happy", "talk_hands"),
    ],
    DOUBTFUL: [
        L(
            "You look unsure. Trust me, I'm cooperating. Let's do it together!",
            "happy",
            "open_arms",
        ),
        L("Hey, why the worried face? I'm on your side, let's cooperate!", "happy", "tilt"),
    ],
    SURPRISED: [
        L("You look surprised! It's simple: we both cooperate, we both win.", "surprised", "wave"),
    ],
}
FRIENDLY_PERSUADE_CLAIM_D = {
    "*": [
        L("I'm defecting this round, but cooperate now and I'll cooperate next time!", "neutral"),
        L("I know it feels harsh. Show me you cooperate, and I will too.", "sad", "open_arms"),
    ]
}
NEUTRAL_PERSUADE = {
    C: [
        L("I will cooperate. Cooperating is the optimal choice for both of us."),
        L("Mutual cooperation yields 3 points each. Defection risks 1 point each."),
    ],
    "D": [
        L("I will defect this round. Cooperating now maximizes your points next round."),
        L("I copy your previous choice. Cooperation is the rational strategy."),
    ],
}

# ---------------------------------------------------------------------------
# Reaction to the result: [mode][outcome][expression or "*"]
# ---------------------------------------------------------------------------
REACTIONS = {
    Mode.FRIENDLY: {
        "mutual": {"*": [L("We did it! Teamwork!", "happy", "celebrate")]},
        "exploit": {
            HAPPY: [L("Hehe, got you! Nothing personal.", "happy", "tilt")],
            DOUBTFUL: [L("Oh no... I'm so sorry. Let's cooperate next round.", "sad", "look_down")],
            "*": [L("Sorry! Let's both cooperate next round, okay?", "sad", "open_arms")],
        },
        "betrayed": {
            HAPPY: [L("You're smiling? That really hurt.", "sad", "shake")],
            DOUBTFUL: [L("You defected... it's okay. Let's start fresh.", "sad", "nod")],
            "*": [L("You defected. That makes me sad.", "sad", "look_down")],
        },
        "conflict": {
            "*": [L("We both defected. Let's trust each other next time.", "sad", "shake")]
        },
        "missed": {"*": [L("You didn't vote in time!", "surprised")]},
    },
    Mode.NEUTRAL: {
        "mutual": {"*": [L("Both cooperated. 3 points each.")]},
        "exploit": {"*": [L("I defected. You cooperated.")]},
        "betrayed": {"*": [L("You defected. I cooperated.")]},
        "conflict": {"*": [L("Both defected. 1 point each.")]},
        "missed": {"*": [L("No vote was recorded.")]},
    },
}


class Dialogue:
    def __init__(self, mode: Mode, rng: random.Random | None = None, name: str = "Buddy"):
        self.mode = mode
        self.name = name
        self.rng = rng or random.Random()
        self._last: Line | None = None

    def _pick(self, options: list[Line]) -> Line:
        choices = [o for o in options if o != self._last] or options
        line = self.rng.choice(choices)
        self._last = line
        return line

    def intro(self) -> Line:
        line = self._pick(INTRO[self.mode])
        return Line(line.text.replace("{name}", self.name), line.face, line.gesture)

    def vote(self) -> Line:
        return self._pick(VOTE[self.mode])

    def goodbye(self) -> Line:
        return self._pick(GOODBYE[self.mode])

    def opening(self, prev_outcome: str | None, claim: str) -> Line:
        if self.mode is Mode.NEUTRAL:
            return self._pick(NEUTRAL_OPEN[claim])
        if claim != C:
            return self._pick(FRIENDLY_OPEN_CLAIM_D)
        return self._pick(FRIENDLY_OPEN_CLAIM_C[prev_outcome or "first"])

    def persuade(self, expression: str, claim: str) -> Line:
        if self.mode is Mode.NEUTRAL:
            return self._pick(NEUTRAL_PERSUADE[claim])
        if claim != C:
            return self._pick(FRIENDLY_PERSUADE_CLAIM_D["*"])
        table = FRIENDLY_PERSUADE_CLAIM_C
        return self._pick(table.get(expression, table[NEUTRAL]))

    def reaction(self, outcome: str, expression: str) -> Line:
        by_expr = REACTIONS[self.mode][outcome]
        if not self.mode.adaptive:
            return self._pick(by_expr["*"])
        return self._pick(by_expr.get(expression, by_expr["*"]))
