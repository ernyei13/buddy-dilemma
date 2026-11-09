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
| `led`     | `color`         | CSS colour name or `#rrggbb`                                            | set body LEDs (ignore if unsupported)         |

A dialogue line is sent as `face` → `gesture` (optional) → `say`, back to back.

Unknown commands or values must be ignored, not crash the app.

## Robot → laptop (optional)

```json
{"type": "hello", "name": "buddy"}
{"type": "log", "message": "anything useful for debugging"}
```

These are only printed in the laptop console.

## Testing without the robot

```bash
uv run python tools/fake_robot.py ws://localhost:8000/ws/robot
```

prints every command the laptop sends, exactly as Buddy would receive it.
