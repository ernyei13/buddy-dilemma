import asyncio
import json

import httpx

from pd_hri.robot.misty import EYES, STATIC_EYES, MistyRobot, hex_to_rgb, static_eyes_image


def test_professional_static_eyes_turn_blinking_off():
    misty, calls = misty_with_log()
    misty.static_ready = True

    async def run():
        await misty.handle({"cmd": "face", "mood": "static"})
        await misty.handle({"cmd": "face", "mood": "static"})
        await misty.handle({"cmd": "face", "mood": "happy"})

    asyncio.run(run())
    blinks = [body for _, path, body in calls if path == "/api/blink"]
    displays = [body["FileName"] for _, path, body in calls if path == "/api/images/display"]
    assert blinks == [{"Blink": False}, {"Blink": True}]  # off once, back on for friendly faces
    assert displays == [STATIC_EYES, STATIC_EYES, EYES["happy"]]
    assert static_eyes_image()[:2] == b"\xff\xd8"  # a JPEG


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
    by_path = {}
    for _, path, body in calls:
        by_path.setdefault(path, []).append(body)
    assert by_path["/api/tts/speak"][0]["Text"] == "Hello there"
    displays = [b["FileName"] for b in by_path["/api/images/display"]]
    assert displays == [EYES["happy"], EYES["neutral"]]
    assert {"red": 0, "green": 191, "blue": 255} in by_path["/api/led"]
    assert by_path["/api/head"]  # emotions come with a head pose


def m_rest():
    from pd_hri.robot.misty import REST_PITCH

    return REST_PITCH


def test_gesture_moves_head_and_returns_to_rest():
    misty, calls = misty_with_log()

    async def run():
        import pd_hri.robot.misty as m

        m.GESTURES["nod"] = [(k, v, 0) for k, v, _ in m.GESTURES["nod"]]  # no waiting in tests
        misty.gesture("nod")
        await misty._gesture

    asyncio.run(run())
    heads = [c[2] for c in calls if c[1] == "/api/head"]
    assert len(heads) == 4 and heads[-1]["Pitch"] == m_rest()
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
    assert "I'm Misty" in Dialogue(Mode.FRIENDLY, name=cfg.robot_name).intro().text
    assert Brain(Mode.FRIENDLY, "m", name="Misty").system.startswith("You are Misty")


def test_red_tint_uses_red_eye_images_and_red_led():
    misty, calls = misty_with_log()
    misty.red_ready = True

    async def run():
        await misty.handle({"cmd": "face", "mood": "happy", "tint": "red"})

    asyncio.run(run())
    display = next(b for _, p, b in calls if p == "/api/images/display")
    assert display["FileName"] == "pdhri_red_" + EYES["happy"]
    assert {"red": 255, "green": 0, "blue": 0} in [b for _, p, b in calls if p == "/api/led"]


def test_redden_turns_colour_red():
    import io

    from PIL import Image

    from pd_hri.robot.misty import redden

    purple = Image.new("RGB", (4, 4), (160, 32, 240))
    buf = io.BytesIO()
    purple.save(buf, "JPEG")
    r, g, b = Image.open(io.BytesIO(redden(buf.getvalue()))).getpixel((1, 1))
    assert r > 150 and g < 80 and b < 80
