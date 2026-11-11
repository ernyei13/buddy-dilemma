"""Scripted robot lines: intro, each round's opening, reactions, and fallback persuasion.

The LLM writes most of the chat; these lines cover the fixed moments and stand in whenever the
LLM is unavailable. Every situation has several variants, and a line is not reused within a
game until all its alternatives have been used.

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
            "Hi, I'm {name}! I'm so happy you're here. Each round we talk, then we both "
            "secretly choose to cooperate or defect.",
            "happy",
            "wave",
        ),
        L(
            "Hello there, I'm {name}! Let's play a little game: we chat, then we each pick "
            "cooperate or defect in secret.",
            "happy",
            "wave",
        ),
    ],
    Mode.NEUTRAL: [
        L(
            "Hello. I am {name}. Each round we talk, then we both choose cooperate or defect "
            "in secret."
        ),
    ],
}
VOTE = {
    Mode.FRIENDLY: [
        L("Time to vote! I've made my choice.", "thinking"),
        L("Okay, decision time. I'm ready!", "thinking"),
        L("Let's vote! Fingers crossed.", "happy"),
        L("Voting now. I've picked mine!", "thinking"),
        L("Here we go, make your choice!", "happy"),
    ],
    Mode.NEUTRAL: [
        L("Please vote now."),
        L("Submit your choice."),
        L("Voting is open."),
        L("Make your selection now."),
    ],
}
GOODBYE = {
    Mode.FRIENDLY: [
        L("That was so much fun! Thank you for playing with me.", "happy", "wave"),
        L("What a game! Thanks for playing, I really enjoyed it.", "happy", "wave"),
    ],
    Mode.NEUTRAL: [L("The game is over. Thank you for participating.")],
}

# ---------------------------------------------------------------------------
# Opening line of each round, by what the robot claims and the previous outcome
# ---------------------------------------------------------------------------
FRIENDLY_OPEN_CLAIM_C = {
    "first": [
        L("If we both cooperate, we each get 3 points. Let's cooperate!", "happy", "open_arms"),
        L("My plan is simple: I cooperate, you cooperate, we both win!", "happy", "talk_hands"),
        L("I'm going to cooperate. Will you be my teammate?", "happy", "open_arms"),
    ],
    "mutual": [
        L("That went great! Let's keep cooperating, partner!", "happy", "celebrate"),
        L("We make a fantastic team! I'm cooperating again.", "happy", "celebrate"),
        L("Six points between us, nice! Same again?", "happy", "nod"),
        L("I loved that round. Let's do it again, together!", "happy", "open_arms"),
        L("You trusted me and I trusted you. Let's keep that going!", "happy", "nod"),
        L("High five! Okay, I'm cooperating again this round.", "happy", "wave"),
    ],
    "betrayed": [
        L("You defected on me... but I'll cooperate again. Please, cooperate too!", "sad"),
        L("Ouch, that stung. I'm still willing to cooperate. Are you?", "sad", "open_arms"),
        L("I'm giving you another chance. I'll cooperate this round.", "sad", "nod"),
        L("That hurt a little. Let's fix it: I cooperate, you cooperate?", "sad", "talk_hands"),
    ],
    "exploit": [
        L("Sorry about last round! This time I'll cooperate, I promise.", "sad", "open_arms"),
        L("Oops, about last round... I'll cooperate now, promise!", "sad", "tilt"),
        L("I owe you one after last round. I'm cooperating now.", "sad", "nod"),
        L("Let me make it up to you. Cooperation from me this time!", "happy", "open_arms"),
    ],
    "conflict": [
        L("We both lost out. Let's both cooperate this time!", "neutral", "open_arms"),
        L("One point each is sad. Let's aim for three!", "sad", "talk_hands"),
        L("We both played it safe. Let's trust each other now.", "neutral", "nod"),
        L("That round was no fun for either of us. Cooperate with me?", "sad", "open_arms"),
    ],
    "missed": [
        L("You didn't vote last time! Let's cooperate this round.", "neutral", "nod"),
        L("Don't forget to vote this time! I'm cooperating.", "happy", "wave"),
        L("We missed a round there. Let's make this one count!", "neutral", "talk_hands"),
    ],
}
FRIENDLY_OPEN_CLAIM_D = [
    L(
        "You defected last round, so this time I'm going to defect too. "
        "But cooperate now, and I'll cooperate with you next round!",
        "neutral",
        "look_down",
    ),
    L(
        "Honestly, I'm defecting this round because you did. "
        "Show me you cooperate, and I'll follow you.",
        "neutral",
        "shake",
    ),
    L(
        "This round I'll defect. I copy what you do, so cooperate and I'll cooperate next!",
        "sad",
        "talk_hands",
    ),
]
NEUTRAL_OPEN = {
    C: [
        L("This round I will cooperate. Mutual cooperation gives 3 points each."),
        L("I will cooperate. The best joint outcome is 3 points each."),
        L("My choice this round is to cooperate."),
        L("I intend to cooperate. I recommend you do the same."),
    ],
    "D": [
        L("This round I will defect. If you cooperate now, I will cooperate next round."),
        L("I will defect this round, copying your previous choice."),
        L("My choice this round is to defect. Cooperation from you changes my next move."),
    ],
}

# ---------------------------------------------------------------------------
# Persuasion during the chat (fallback when there is no LLM or it repeats itself)
# ---------------------------------------------------------------------------
FRIENDLY_PERSUADE_CLAIM_C = {
    HAPPY: [
        L("I love your smile! We make a great team, let's both cooperate.", "happy", "celebrate"),
        L("You look happy, and that makes me happy too! Cooperate with me?", "happy", "open_arms"),
        L("That smile tells me we're on the same page. Cooperate?", "happy", "nod"),
        L("You're in a good mood! Let's keep it that way: cooperate.", "happy", "talk_hands"),
    ],
    NEUTRAL: [
        L("I can't quite read your face. How do you feel? Let's cooperate!", "neutral", "tilt"),
        L("Remember: if we both cooperate, we both get 3 points.", "happy", "talk_hands"),
        L("What are you thinking? I'm hoping we cooperate.", "thinking", "tilt"),
        L("Think of us as a team. Teams cooperate!", "happy", "open_arms"),
        L("Three points each beats one point each, right?", "happy", "talk_hands"),
    ],
    DOUBTFUL: [
        L(
            "You look unsure. Trust me, I'm cooperating. Let's do it together!",
            "happy",
            "open_arms",
        ),
        L("Hey, why the worried face? I'm on your side, let's cooperate!", "happy", "tilt"),
        L("I see some doubt there. What would make you trust me?", "thinking", "tilt"),
        L("Don't worry, I won't let you down. Cooperate with me?", "happy", "nod"),
    ],
    SURPRISED: [
        L("You look surprised! It's simple: we both cooperate, we both win.", "surprised", "wave"),
        L("Whoa, that face! Did I say something unexpected?", "surprised", "tilt"),
        L("Surprised? Cooperating really is the best for both of us!", "surprised", "talk_hands"),
    ],
}
FRIENDLY_PERSUADE_CLAIM_D = {
    "*": [
        L("I'm defecting this round, but cooperate now and I'll cooperate next time!", "neutral"),
        L("I know it feels harsh. Show me you cooperate, and I will too.", "sad", "open_arms"),
        L("I just copy you. Cooperate, and next round I'm all yours!", "neutral", "talk_hands"),
        L("Let's break the cycle. You cooperate, and I'll follow.", "sad", "nod"),
    ]
}
NEUTRAL_PERSUADE = {
    C: [
        L("I will cooperate. Cooperating is the optimal choice for both of us."),
        L("Mutual cooperation yields 3 points each. Defection risks 1 point each."),
        L("Cooperation maximizes the total score."),
        L("Over many rounds, cooperation produces the highest payoff."),
        L("A defection now lowers the expected score of the next rounds."),
    ],
    "D": [
        L("I will defect this round. Cooperating now maximizes your points next round."),
        L("I copy your previous choice. Cooperation is the rational strategy."),
        L("Your cooperation now determines my cooperation next round."),
        L("Defection by both players yields only 1 point each."),
    ],
}

# ---------------------------------------------------------------------------
# Reaction to the result: [mode][outcome][expression or "*"]
# ---------------------------------------------------------------------------
REACTIONS = {
    Mode.FRIENDLY: {
        "mutual": {
            "*": [
                L("We did it! Teamwork!", "happy", "celebrate"),
                L("Yes! Three points each!", "happy", "celebrate"),
                L("I knew I could trust you!", "happy", "wave"),
                L("That's what I call a team!", "happy", "celebrate"),
            ]
        },
        "exploit": {
            HAPPY: [
                L("Hehe, got you! Nothing personal.", "happy", "tilt"),
                L("Oh, you're smiling? Good sport!", "happy", "nod"),
            ],
            DOUBTFUL: [
                L("Oh no... I'm so sorry. Let's cooperate next round.", "sad", "look_down"),
                L("I see that face. I'm sorry, I'll make it right.", "sad", "open_arms"),
            ],
            "*": [
                L("Sorry! Let's both cooperate next round, okay?", "sad", "open_arms"),
                L("Oops. I'll make it up to you.", "sad", "look_down"),
                L("That wasn't nice of me. Next round, together?", "sad", "nod"),
            ],
        },
        "betrayed": {
            HAPPY: [
                L("You're smiling? That really hurt.", "sad", "shake"),
                L("Hey, don't look so pleased! That stung.", "angry", "shake"),
            ],
            DOUBTFUL: [
                L("You defected... it's okay. Let's start fresh.", "sad", "nod"),
                L("I forgive you. Let's try again.", "sad", "open_arms"),
            ],
            "*": [
                L("You defected. That makes me sad.", "sad", "look_down"),
                L("Oh... I really thought we were a team.", "sad", "look_down"),
                L("Ouch. I trusted you.", "sad", "shake"),
            ],
        },
        "conflict": {
            "*": [
                L("We both defected. Let's trust each other next time.", "sad", "shake"),
                L("One point each. We can do better!", "sad", "talk_hands"),
                L("Neither of us trusted the other. Next time?", "sad", "tilt"),
            ]
        },
        "missed": {
            "*": [
                L("You didn't vote in time!", "surprised"),
                L("Oh, no vote this time!", "surprised", "tilt"),
            ]
        },
    },
    Mode.NEUTRAL: {
        "mutual": {"*": [L("Both cooperated. 3 points each."), L("Mutual cooperation.")]},
        "exploit": {"*": [L("I defected. You cooperated."), L("Outcome: 5 for me, 0 for you.")]},
        "betrayed": {"*": [L("You defected. I cooperated."), L("Outcome: 0 for me, 5 for you.")]},
        "conflict": {"*": [L("Both defected. 1 point each."), L("Mutual defection.")]},
        "missed": {"*": [L("No vote was recorded.")]},
    },
}


class Dialogue:
    def __init__(self, mode: Mode, rng: random.Random | None = None, name: str = "Buddy"):
        self.mode = mode
        self.name = name
        self.rng = rng or random.Random()
        self._used: set[str] = set()
        self._last: Line | None = None

    def _pick(self, options: list[Line]) -> Line:
        """Prefer lines not used yet this game; never the same line twice in a row."""
        fresh = [o for o in options if o.text not in self._used]
        choices = fresh or [o for o in options if o != self._last] or options
        line = self.rng.choice(choices)
        self._used.add(line.text)
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
        options = by_expr.get(expression, []) + by_expr["*"]
        return self._pick(options)
