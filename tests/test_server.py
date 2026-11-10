from fastapi.testclient import TestClient

from pd_hri.config import Config
from pd_hri.server import create_app


def test_index_and_status(tmp_path):
    client = TestClient(create_app(Config(data_dir=tmp_path)))
    assert client.get("/").status_code == 200
    assert client.get("/static/app.js").status_code == 200
    status = client.get("/api/status").json()
    assert status["robot"] == "mock" and status["running"] is False


def test_screen_socket_classifies_expressions(tmp_path):
    client = TestClient(create_app(Config(data_dir=tmp_path)))
    with client.websocket_connect("/ws/screen") as ws:
        assert ws.receive_json()["type"] == "status"
        ws.send_json(
            {"type": "expression", "scores": {"mouthSmileLeft": 0.9, "mouthSmileRight": 0.9}}
        )
        assert ws.receive_json() == {"type": "expression", "label": "happy"}
        ws.send_json({"type": "expression", "label": "doubtful"})
        assert ws.receive_json() == {"type": "expression", "label": "doubtful"}


def test_robot_adapter_connection_updates_status(tmp_path):
    client = TestClient(create_app(Config(robot="buddy", data_dir=tmp_path)))
    with client.websocket_connect("/ws/screen") as screen:
        screen.receive_json()
        with client.websocket_connect("/ws/robot") as robot:
            robot.send_json({"type": "hello", "name": "test"})
            assert screen.receive_json()["robots_connected"] == 1
            robot.send_json({"type": "speech_done"})
            assert screen.receive_json() == {"type": "robot_speech_done"}
