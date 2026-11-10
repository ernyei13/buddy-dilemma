# Buddy app (Android)

A small Android app that turns Buddy into the robot body for the study. It uses Buddy's
**native face, voice, head movements and LEDs** through Blue Frog's SDK. No Unity.

The laptop does all the thinking: camera, mic, speech recognition, LLM and game logic. This app
connects to it over Wi-Fi and carries out its commands:

| Laptop sends | Buddy does (SDK call) |
|---|---|
| `say` | speaks with its own voice, mouth moving: `Speech.startSpeaking(text, LabialExpression, callback)` |
| `face` | native expression: `UI.setMood(FacialExpression.HAPPY …)`, which also sets matching LEDs |
| `gesture` | head nods/shakes via the yes/no motors (`USB.buddySayYes` / `buddySayNo`), plus facial events (`UI.playFacialEvent`) |
| `led` | `USB.updateAllLed("#rrggbb")` |

When Buddy finishes a sentence, the app tells the laptop (`speech_done`) so the participant's mic
unmutes right away.

The calls follow the **Buddy SDK 2.4 user guide**.

## What you need

- The **Buddy SDK login** (Maven username and password) from Blue Frog Robotics or your
  teaching team.
- **Android Studio** (free).
- Developer access to install apps on Buddy (USB/adb, as described in the SDK guide).

## Setup

1. In Android Studio choose **File → Open** and select this `buddy_app` folder. If it offers to
   create or update the Gradle wrapper, accept.
2. Copy `credentials.gradle.example` to `credentials.gradle` in this folder and fill in your
   Blue Frog login. The file is git-ignored; never commit it.
3. Click **Sync Project with Gradle Files**. This downloads the Buddy SDK.
4. **Fix imports if needed.** The SDK guide gives the class names (`FacialExpression`,
   `LabialExpression`, `FacialEvent`, `ITTSCallback`, `IUsbCommadRsp`) but not their package
   paths. If any `import com.bfr.buddy…` line in `MainActivity.java` is red, delete it, click
   the class name in the code and press **Alt+Enter → Import class**.
5. Connect Buddy and press **Run ▶** to install the app.

## Running a session

1. Put the laptop and Buddy on the **same Wi-Fi**. If the university network blocks
   device-to-device traffic, use a phone hotspot.
2. On the laptop, run:
   ```bash
   uv run pd-hri --robot buddy
   ```
   It prints the robot address, for example `ws://192.168.1.10:8000/ws/robot`.
3. On Buddy, open **Buddy Dilemma**, type that address and press **Connect**. The panel hides
   once connected, and the app remembers the address. Long-press the status text in the top
   left to change it.
4. The laptop start screen shows **"Buddy — connected ✅"**. Pick a mode and press Start.

## Check on the real robot

These parts couldn't be tested without a robot:

- **Head angles.** The guide calls the angle a "target", but its own example moves the head
  back with the negative angle, as if angles were relative. The app follows the example. If
  nods drift or don't return to center, set `HEAD_ANGLES_ARE_RELATIVE = false` in
  `MainActivity.java`.
- **The speech callback.** If `new ITTSCallback.Stub()` doesn't compile with your SDK version,
  replace the body of `say()` with the one-line fallback in the comment there.
- **Gesture feel.** The angles and speeds of each gesture (`nod`, `shake`, `tilt`, `look_down`,
  `celebrate`) are in `gesture()`. Tune them until they look natural.

## Testing without Buddy

From the repo root, run:

```bash
uv run python tools/fake_robot.py
```

It connects like this app does, prints every command Buddy would receive, and sends
`speech_done` back.
