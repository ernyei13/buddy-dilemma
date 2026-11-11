# Robot Dilemma: a Prisoner's Dilemma HRI study

DD2413 Social Robotics (KTH), project and Lab 1.

A participant **talks with a social robot (Misty II or Buddy) for 60 seconds**. Then both secretly vote
**Cooperate** or **Defect** within 10 seconds, and the screen shows the result. This repeats
for 5 rounds.

- The robot listens (local speech recognition) and answers (local LLM).
- It watches the person's **facial expression** (webcam) and adapts what it says and shows.

**Everything runs locally on the laptop.** There are no cloud APIs and no API keys. After the
models are downloaded once, it works offline.

| Part | Runs on | Tool |
|---|---|---|
| Facial expression | browser, laptop GPU/CPU | MediaPipe Face Landmarker |
| Speech to text | laptop CPU | faster-whisper (`base.en`) |
| Conversation | laptop | Ollama (`qwen2.5:3b`) |
| Text to speech | the robot's own voice, or a local macOS voice (mock) | — |

## Modes (experimental conditions)

| Mode | What Buddy says | How Buddy votes | Adapts to face |
|---|---|---|---|
| `honest` | Tells the truth about its vote | Tit-for-Tat (cooperates first, then copies you) | yes |
| `liar` | Always promises to cooperate | Defects in rounds 2 and 4 | yes |
| `neutral` | Flat, factual answers | Tit-for-Tat | no (control) |

## Setup (once)

Needs Python 3.10+, [uv](https://docs.astral.sh/uv/) and [Ollama](https://ollama.com).

```bash
uv sync
brew install ollama            # or the installer from ollama.com
ollama serve                   # leave running (the macOS app does this for you)
ollama pull qwen2.5:3b         # ~1.9 GB; smarter but slower: qwen2.5:7b
uv run python tools/fetch_assets.py   # face model + Whisper model for offline use
```

## Run

```bash
uv run pd-hri                  # mock robot: avatar + voice in the browser
uv run pd-hri --fast           # 20 s chat for quick testing
uv run pd-hri --robot misty --misty-ip 192.168.1.50   # real Misty II (see below)
uv run pd-hri --robot buddy    # real Buddy via its Android app (see below)
uv run pd-hri --no-llm         # scripted lines only, no Ollama needed
uv run pd-hri --llm-model qwen2.5:7b --stt-model small.en
```

Open http://localhost:8000 in **Chrome or Safari**, allow the camera and microphone, enter a
participant ID, pick a mode and press **Start**. The start screen shows a check for each part:
robot, camera, mic, speech recognition and LLM.

You can see yourself in the corner with the detected expression, the mic level, and the
conversation on the right.

**Keys:** `C`/`D` vote · `1`–`4` simulate happy/neutral/doubtful/surprised · `0` back to
camera · `E` hide or show the self-view (hide it for real participants) · `T` type as the
participant (testing without a mic) · `Shift+Q` abort.

## How it works (sense → plan → act)

```
 webcam ─► face.js (MediaPipe) ─► expression.py ─┐
 mic ────► voice.js (detects speech) ─► stt.py (Whisper) ─┤
                                                         ▼
 START ─► session.py: CHAT 60 s ─► VOTE 10 s ─► RESULT ─► next round
              │  robot vote = game.py strategy for the mode
              │  reply      = llm.py (Ollama) with mode + real vote + face + time left
              │               (falls back to dialogue.py scripted lines)
              ▼
          Robot interface: say / face / gesture / led
              ├─ MockRobot   → avatar + local text-to-speech in the browser
              └─ RemoteRobot → Buddy app over WebSocket (docs/protocol.md)
```

During the chat Buddy replies to each thing the person says. If they stay quiet for 7 s, Buddy
speaks up. The mic is muted while Buddy talks so it doesn't hear itself.

| File | What it does |
|---|---|
| `src/pd_hri/config.py` | timings, rounds, payoffs, the liar's rounds, model names |
| `src/pd_hri/game.py` | rules, scoring, each mode's strategy |
| `src/pd_hri/llm.py` | **LLM personality per mode**: edit the prompts here |
| `src/pd_hri/dialogue.py` | scripted lines (intro, reactions, fallback when there's no LLM) |
| `src/pd_hri/stt.py` | local Whisper speech recognition |
| `src/pd_hri/expression.py` | blendshapes → happy / neutral / doubtful / surprised |
| `src/pd_hri/session.py` | round state machine, conversation loop, logging |
| `src/pd_hri/server.py` | web server plus the `/ws/screen` and `/ws/robot` sockets |
| `src/pd_hri/web/` | screen: timer, voting, chat, self-view, mic capture, mock avatar |
| `buddy_app/` | Android app for Buddy: native face, voice, head, LEDs (Buddy SDK) |
| `src/pd_hri/robot/misty.py` | Misty II backend: speech, eye images, head/arms, LED |
| `tools/fake_robot.py` | prints the commands a robot would receive |
| `tools/fake_misty.py` | pretends to be Misty on your laptop, for testing |
| `tools/fetch_assets.py` | downloads the face and speech models for offline use |

## Running on Misty II

Misty is controlled over its built-in HTTP API, so **nothing is installed on the robot**. The
laptop sends the robot's speech, eye images, head/arm movements and chest LED; Misty's own voice
speaks and its eyes show the expression.

1. Switch Misty on and connect it to the **same Wi-Fi as the laptop** (Misty App or Misty
   Studio). Note its **IP address**, shown in the Misty App.
2. Check the laptop can reach it: open `http://<misty-ip>/api/device` in a browser. You should
   see JSON with Misty's info.
3. Run:
   ```bash
   uv run pd-hri --robot misty --misty-ip <misty-ip>
   ```
4. Open http://localhost:8000. The start screen shows "Robot: Misty — connected ✅".

The laptop camera and mic face the participant, next to Misty. The robot introduces itself as
"Misty". Tune eye images and movements in `src/pd_hri/robot/misty.py` (the `EYES` and
`GESTURES` tables). If a head move goes the wrong way, flip its sign there.

**Test without Misty:** `uv run python tools/fake_misty.py` prints every command; then run
`uv run pd-hri --robot misty --misty-ip localhost:8800`.

## Running on Buddy

Buddy runs a small Android app ([`buddy_app/`](buddy_app/README.md)) that uses its **native
face, voice, head movements and LEDs** through the Buddy SDK. Camera, mic, speech recognition
and the LLM all stay on the laptop.

1. Build and install the app with Android Studio, following [`buddy_app/README.md`](buddy_app/README.md).
   You need the Buddy SDK login from Blue Frog or your teaching team.
2. Put the laptop and Buddy on the same Wi-Fi network.
3. Run `uv run pd-hri --robot buddy`, then type the printed `ws://…/ws/robot` address in the app
   on Buddy and press Connect.
4. The start screen shows "Buddy — connected ✅". Place the laptop's camera and mic in front of
   the participant, next to Buddy.

## Data

Each session writes `data/<date>_<participant>_<mode>.csv` with one row per round: votes,
points, vote time, expression counts, the expression right after the reveal, and the full
dialogue (`Buddy: … | Human: …`). The `data/` folder is git-ignored. **Never commit participant data.**

## Development

```bash
uv run pytest           # tests
uv run ruff check .     # lint
uv run ruff format .    # format
```

CI runs lint and tests on every push. Work on a branch and open a PR to `main`.

### Suggested team split

- **Perception:** `web/face.js`, `expression.py`, `web/voice.js`, `stt.py`
- **Conversation:** `llm.py` prompts, `dialogue.py` lines, `session.py` turn-taking
- **Study logic and data:** `game.py`, `config.py`, logging, analysis
- **Buddy integration:** `buddy_app/`, testing on the robot
