# Buddy Dilemma: a Prisoner's Dilemma HRI study

DD2413 Social Robotics (KTH), project and Lab 1.

A participant talks with the social robot **Buddy** for 60 seconds. Then both secretly vote
**Cooperate** or **Defect** within 10 seconds, and the screen shows the result. This repeats
for 5 rounds. Buddy reads the participant's **facial expression** from a webcam and adapts what
it says and shows.

## Modes (experimental conditions)

| Mode | What Buddy says | How Buddy votes | Adapts to face |
|---|---|---|---|
| `honest` | Tells the truth about its vote | Tit-for-Tat (cooperates first, then copies you) | yes |
| `liar` | Always promises to cooperate | Defects in rounds 2 and 4 | yes |
| `neutral` | Flat, factual lines | Tit-for-Tat | no (control) |

## Quick start

Needs Python 3.10+ and [uv](https://docs.astral.sh/uv/).

```bash
uv sync
uv run pd-hri              # mock robot: avatar + voice in the browser
```

Open http://localhost:8000, allow the camera, enter a participant ID, pick a mode and press **Start**.

```bash
uv run pd-hri --fast       # short timings (12 s chat) for testing
uv run pd-hri --robot buddy   # real Buddy via the adapter (see below)
```

**Keys:** `C`/`D` vote · `1`–`4` simulate happy/neutral/doubtful/surprised · `0` back to
camera · `E` show the camera and the detected expression · `Shift+Q` abort.

The face tracker (MediaPipe) is loaded from a CDN, so the laptop needs internet when the page loads.

## How it works (sense → plan → act)

```
 webcam ─► face.js (MediaPipe blendshapes) ─► expression.py (classify + smooth)
                                                     │
 START ─► session.py: CHAT 60 s ─► VOTE 10 s ─► RESULT ─► next round
              │  robot vote = game.py strategy for the mode
              │  line       = dialogue.py (mode × planned vote × expression)
              ▼
          Robot interface: say / face / gesture / led
              ├─ MockRobot   → avatar + text-to-speech in the browser
              └─ RemoteRobot → Buddy app over WebSocket (docs/protocol.md)
```

| File | What it does |
|---|---|
| `src/pd_hri/config.py` | timings, rounds, payoffs, the liar's defect rounds |
| `src/pd_hri/game.py` | rules, scoring, each mode's strategy |
| `src/pd_hri/dialogue.py` | **all of Buddy's lines**: edit here |
| `src/pd_hri/expression.py` | blendshapes → happy / neutral / doubtful / surprised |
| `src/pd_hri/session.py` | the round state machine and logging |
| `src/pd_hri/server.py` | web server plus the `/ws/screen` and `/ws/robot` sockets |
| `src/pd_hri/web/` | participant screen: timer, voting, results, mock avatar, webcam |
| `buddy_adapter/` | Unity C# bridge for Buddy (fill in the SDK calls) |
| `tools/fake_robot.py` | prints the commands a robot would receive |

## Running on Buddy

1. Follow [`buddy_adapter/README.md`](buddy_adapter/README.md) to put `BuddyBridge.cs` in a Buddy app.
2. Put the laptop and Buddy on the same Wi-Fi network.
3. Run `uv run pd-hri --robot buddy`, then set the printed `ws://…/ws/robot` URL in the app.
4. The start screen shows "Buddy — connected ✅".

## Data

Each session writes `data/<date>_<participant>_<mode>.csv` with one row per round: votes,
points, vote time, expression counts during chat and voting, the expression right after the
reveal, and Buddy's lines. The `data/` folder is git-ignored. **Never commit participant data.**

## Development

```bash
uv run pytest           # tests
uv run ruff check .     # lint
uv run ruff format .    # format
```

CI runs lint and tests on every push. Work on a branch and open a PR to `main`.

### Suggested team split

- **Perception:** `web/face.js`, `expression.py` (tune thresholds with the `E` debug view)
- **Interaction logic:** `session.py`, `game.py`, `config.py`, logging
- **Robot behavior:** `dialogue.py` lines, faces and gestures
- **Buddy integration:** `buddy_adapter/`, testing on the robot
