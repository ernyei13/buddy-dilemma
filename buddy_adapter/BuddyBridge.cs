// BuddyBridge: the only Buddy-specific code.
//
// Drop this MonoBehaviour into a Buddy (Unity) app. It connects to the laptop as a WebSocket
// client and turns the JSON commands from docs/protocol.md into Buddy SDK calls.
//
// Everything marked TODO(SDK) must be checked against the Buddy SDK docs: the SDK names in the
// comments are best guesses, not verified.

using System;
using System.Collections.Concurrent;
using System.Net.WebSockets;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using UnityEngine;

public class BuddyBridge : MonoBehaviour
{
    [Tooltip("Printed by `uv run pd-hri --robot buddy` on the laptop")]
    public string serverUrl = "ws://192.168.1.10:8000/ws/robot";

    [Serializable]
    private class Command
    {
        public string cmd;
        public string text;
        public string mood;
        public string name;
        public string color;
    }

    // Commands arrive on a background thread; SDK calls must happen on Unity's main thread.
    private readonly ConcurrentQueue<Command> _queue = new ConcurrentQueue<Command>();
    private CancellationTokenSource _cts;

    private void Start()
    {
        _cts = new CancellationTokenSource();
        _ = RunAsync(_cts.Token);
    }

    private void OnDestroy() => _cts?.Cancel();

    private void Update()
    {
        while (_queue.TryDequeue(out var c))
        {
            try { Execute(c); }
            catch (Exception e) { Debug.LogWarning($"[BuddyBridge] {c.cmd} failed: {e.Message}"); }
        }
    }

    private async Task RunAsync(CancellationToken ct)
    {
        while (!ct.IsCancellationRequested)
        {
            using (var ws = new ClientWebSocket())
            {
                try
                {
                    await ws.ConnectAsync(new Uri(serverUrl), ct);
                    Debug.Log($"[BuddyBridge] connected to {serverUrl}");
                    await SendAsync(ws, "{\"type\":\"hello\",\"name\":\"buddy\"}", ct);

                    var buffer = new byte[8192];
                    var sb = new StringBuilder();
                    while (ws.State == WebSocketState.Open && !ct.IsCancellationRequested)
                    {
                        var result = await ws.ReceiveAsync(new ArraySegment<byte>(buffer), ct);
                        if (result.MessageType == WebSocketMessageType.Close) break;
                        sb.Append(Encoding.UTF8.GetString(buffer, 0, result.Count));
                        if (!result.EndOfMessage) continue;
                        _queue.Enqueue(JsonUtility.FromJson<Command>(sb.ToString()));
                        sb.Clear();
                    }
                }
                catch (Exception e) when (!ct.IsCancellationRequested)
                {
                    Debug.LogWarning($"[BuddyBridge] connection error: {e.Message}");
                }
            }
            await Task.Delay(2000, ct); // reconnect loop
        }
    }

    private static Task SendAsync(ClientWebSocket ws, string json, CancellationToken ct) =>
        ws.SendAsync(new ArraySegment<byte>(Encoding.UTF8.GetBytes(json)),
                     WebSocketMessageType.Text, true, ct);

    // ------------------------------------------------------------------ command mapping
    private void Execute(Command c)
    {
        switch (c.cmd)
        {
            case "say": Say(c.text); break;
            case "face": Face(c.mood); break;
            case "gesture": Gesture(c.name); break;
            case "led": Led(c.color); break;
            default: Debug.Log($"[BuddyBridge] ignoring unknown cmd {c.cmd}"); break;
        }
    }

    private void Say(string text)
    {
        // TODO(SDK): stop current speech, then speak without blocking.
        // e.g. Buddy.Vocal.StopSpeaking(); Buddy.Vocal.Say(text);
        Debug.Log($"[BuddyBridge] say: {text}");
    }

    private void Face(string mood)
    {
        // TODO(SDK): map our moods to Buddy's facial moods.
        // e.g. Buddy.Behaviour.SetMood(Mood.HAPPY);
        //   neutral->NEUTRAL, happy->HAPPY, sad->SAD, angry->ANGRY, surprised->SURPRISED,
        //   thinking->THINKING, listening->LISTENING
        Debug.Log($"[BuddyBridge] face: {mood}");
    }

    private void Gesture(string name)
    {
        // TODO(SDK): short head/body movements (keep each under ~2 s).
        //   nod: head pitch down/up, shake: head yaw left/right, tilt: head roll or yaw + pause,
        //   look_down: head pitch down for ~1.5 s, celebrate: small body turn or wheel wiggle
        Debug.Log($"[BuddyBridge] gesture: {name}");
    }

    private void Led(string color)
    {
        // TODO(SDK): set body LEDs if available; otherwise ignore.
        Debug.Log($"[BuddyBridge] led: {color}");
    }
}
