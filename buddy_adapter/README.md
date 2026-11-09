# Buddy adapter

Buddy apps are built with Unity and the Buddy SDK (C#). This folder holds the one script
that connects Buddy to the laptop: [`BuddyBridge.cs`](BuddyBridge.cs).

## Setup

1. Create or open a Buddy app project with the Buddy SDK, following Blue Frog Robotics' docs.
2. Copy `BuddyBridge.cs` into `Assets/Scripts/` and add it to a GameObject in the app's scene.
3. Set `serverUrl` to the URL the laptop prints, for example `ws://192.168.1.10:8000/ws/robot`.
   The laptop and Buddy must be on the **same Wi-Fi network**.
4. Fill in the four `TODO(SDK)` methods (`Say`, `Face`, `Gesture`, `Led`) with the real SDK calls.
5. Deploy to Buddy, then start the laptop with `uv run pd-hri --robot buddy`. The start
   screen should show "Buddy — connected".

## Before the real robot is available

Run `uv run python tools/fake_robot.py` to see exactly which commands Buddy will receive.

## Checklist

- [ ] The Buddy SDK version supports `System.Net.WebSockets.ClientWebSocket` (.NET 4.x).
      If it doesn't, swap it for a Unity WebSocket package such as NativeWebSocket. Only `RunAsync` changes.
- [ ] Speech starts without blocking and interrupts the previous line.
- [ ] All 7 moods map to a Buddy face.
- [ ] All 5 gestures finish within about 2 s.
