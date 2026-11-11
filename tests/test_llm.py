import asyncio
import json

import httpx

from pd_hri.game import Mode
from pd_hri.llm import MODE_PROMPTS, Brain


def brain_with(handler, mode=Mode.FRIENDLY) -> Brain:
    b = Brain(mode, "test-model")
    b._http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return b


def test_reply_parses_structured_output_and_keeps_history():
    sent = {}

    def handler(request):
        sent.update(json.loads(request.content))
        content = json.dumps({"text": "Trust me, partner!", "face": "happy", "gesture": "tilt"})
        return httpx.Response(200, json={"message": {"content": content}})

    b = brain_with(handler)
    b.note_robot_line("Hi, I'm Buddy!")
    line = asyncio.run(
        b.reply("Round 1/5. Your real vote this round: DEFECT.", "will you cooperate?")
    )

    assert (line.text, line.face, line.gesture) == ("Trust me, partner!", "happy", "tilt")
    assert sent["model"] == "test-model" and sent["stream"] is False
    assert sent["messages"][0]["role"] == "system"
    assert MODE_PROMPTS[Mode.FRIENDLY] in sent["messages"][0]["content"]
    assert [m["role"] for m in b.messages] == ["assistant", "user", "assistant"]
    assert "will you cooperate?" in b.messages[1]["content"]


def test_reply_returns_none_on_bad_output_or_offline():
    bad = brain_with(lambda r: httpx.Response(200, json={"message": {"content": "not json"}}))
    assert asyncio.run(bad.reply("ctx", None)) is None

    def offline(request):
        raise httpx.ConnectError("no ollama")

    assert asyncio.run(brain_with(offline).reply("ctx", "hi")) is None


def test_gesture_none_maps_to_no_gesture():
    content = json.dumps({"text": "Okay.", "face": "neutral", "gesture": "none"})
    b = brain_with(lambda r: httpx.Response(200, json={"message": {"content": content}}))
    assert asyncio.run(b.reply("ctx", None)).gesture is None


def test_reply_without_words_is_rejected():
    content = json.dumps({"text": "...", "face": "neutral", "gesture": "none"})
    b = brain_with(lambda r: httpx.Response(200, json={"message": {"content": content}}))
    assert asyncio.run(b.reply("ctx", None)) is None


def test_vote_rule_truth_and_lies():
    from pd_hri.llm import vote_rule

    assert "LIE" in vote_rule("D", "C") and "Never reveal" in vote_rule("D", "C")
    assert "LIE" in vote_rule("C", "D")
    assert "WILL COOPERATE" in vote_rule("C", "C")
    assert "Do NOT say you will cooperate" in vote_rule("D", "D")


def test_face_rule_per_mode():
    from pd_hri.llm import face_rule

    assert "SMILING" in face_rule(Mode.FRIENDLY, "happy")
    assert "DOUBTFUL" in face_rule(Mode.FRIENDLY, "doubtful")
    assert face_rule(Mode.NEUTRAL, "happy") == ""  # neutral mode ignores the face


def test_too_similar_catches_repeats_but_not_new_lines():
    from pd_hri.llm import too_similar

    said = ["I love your smile! Let's both cooperate this round."]
    assert too_similar("I love your smile! Let's cooperate again this round.", said)
    assert too_similar("I love your smile, friend.", said)  # same opening words
    assert not too_similar("What are you planning to choose?", said)


def test_angle_changes_every_turn():
    b = Brain(Mode.FRIENDLY, "m")
    angles = [b._pick_angle() for _ in range(4)]
    assert len(set(angles)) == 4
