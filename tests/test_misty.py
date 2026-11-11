import asyncio
import json

import httpx

from pd_hri.robot.misty import EYES, MistyRobot, hex_to_rgb


def misty_with_log():
    calls = []

    def handler(request):
        body = json.loads(request.content) if request.content else None
        calls.append((request.method, request.url.path, body))
        return httpx.Response(200, json={"status": "Success"})

    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return MistyRobot("192.168.1.50", http=http), calls


def test_say_face_led_map_to_misty_api():
    misty, calls = misty_with_log()

    async def run():
        await misty.handle({"cmd": "say", "text": "Hello there"})
        await misty.handle({"cmd": "face", "mood": "happy"})
        await misty.handle({"cmd": "led", "color": "#00BFFF"})
        await misty.handle({"cmd": "face", "mood": "unknown-mood"})

    asyncio.run(run())
    paths = [c[1] for c in calls]
    assert paths == ["/api/tts/speak", "/api/images/display", "/api/led", "/api/images/display"]
    assert calls[0][2]["Text"] == "Hello there" and calls[0][2]["Flush"] is True
    assert calls[1][2]["FileName"] == EYES["happy"]
    assert calls[2][2] == {"red": 0, "green": 191, "blue": 255}
    assert calls[3][2]["FileName"] == EYES["neutral"]


def test_gesture_moves_head_and_returns_to_center():
    misty, calls = misty_with_log()

    async def run():
        import pd_hri.robot.misty as m

        m.GESTURES["nod"] = [(k, v, 0) for k, v, _ in m.GESTURES["nod"]]  # no waiting in tests
        misty.gesture("nod")
        await misty._gesture

    asyncio.run(run())
    heads = [c[2] for c in calls if c[1] == "/api/head"]
    assert len(heads) == 4 and heads[-1]["Pitch"] == 0
    assert all(h["Units"] == "degrees" for h in heads)


def test_speech_done_event_is_forwarded():
    done = []

    async def on_done():
        done.append(True)

    misty = MistyRobot("192.168.1.50", on_speech_done=on_done)

    async def run():
        await misty.handle_event(json.dumps("Registration Status: subscribed"))
        await misty.handle_event(json.dumps({"eventName": "pdhri_tts", "message": {}}))
        await misty.http.aclose()

    asyncio.run(run())
    assert done == [True]


def test_hex_to_rgb():
    assert hex_to_rgb("#FF0080") == (255, 0, 128)
    assert hex_to_rgb("deepskyblue") is None


def test_robot_name_follows_backend():
    from pd_hri.config import Config
    from pd_hri.dialogue import Dialogue
    from pd_hri.game import Mode
    from pd_hri.llm import Brain

    cfg = Config(robot="misty", misty_ip="1.2.3.4")
    assert cfg.robot_name == "Misty" and Config().robot_name == "Buddy"
    assert "I'm Misty" in Dialogue(Mode.HONEST, name=cfg.robot_name).intro().text
    assert Brain(Mode.LIAR, "m", name="Misty").system.startswith("You are Misty")
