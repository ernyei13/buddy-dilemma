# Robot protocol

The laptop runs the whole interaction. A robot is only a body: it connects to the laptop as a
**WebSocket client** and executes JSON commands.

```
ws://<laptop-ip>:8000/ws/robot
```

Start the laptop with `uv run pd-hri --robot buddy`; it prints the exact URL. The start screen
shows whether a robot is connected.

## Laptop → robot

Every message is one JSON object with a `cmd` field.

| cmd       | fields          | values                                                                 | robot should                                  |
|-----------|-----------------|------------------------------------------------------------------------|-----------------------------------------------|
| `say`     | `text` (string) | any sentence                                                           | start speaking **without blocking**; interrupt any current speech |
| `face`    | `mood`          | `neutral` `happy` `sad` `angry` `surprised` `thinking` `listening`     | show that facial expression                   |
| `gesture` | `name`          | `nod` `shake` `tilt` `look_down` `celebrate`                           | play a short (≤ 2 s) head/body movement        |
| `led`     | `color`         | `#rrggbb`                                                               | set body LEDs (ignore if unsupported)         |

A dialogue line is sent as `face` → `gesture` (optional) → `say`, back to back. While the
laptop waits for the LLM, it sends `face: thinking`.

The robot does **not** need a camera, mic, speech recognition or LLM: the laptop handles all
of these. Buddy only executes these four commands with its own voice and body.

Unknown commands or values must be ignored, not crash the app.

## Robot → laptop (optional)

```json
{"type": "hello", "name": "buddy"}
{"type": "speech_done"}
{"type": "log", "message": "anything useful for debugging"}
```

`speech_done` is sent when Buddy finishes a `say`. The laptop then unmutes the participant's
mic right away, instead of waiting for its estimate of how long the line takes. The others are
only printed in the laptop console.

## Testing without the robot

```bash
uv run python tools/fake_robot.py ws://localhost:8000/ws/robot
```

prints every command the laptop sends, exactly as Buddy would receive it.
