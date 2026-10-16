"""独立进程中使用真实 ASGI/OneBot 握手，不连接 QQ 或外部服务。"""

import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


class TransportTests(unittest.TestCase):
    def test_reverse_websocket_token_and_group_ping(self):
        root = Path(__file__).resolve().parent.parent
        program = r'''
import sys
sys.path.insert(0, sys.argv[1])
import nonebot
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect
from app.config import Settings
from bot import build_bot
settings = Settings(onebot_access_token="0123456789abcdef", allowed_groups=frozenset({"20000"}))
build_bot(settings)
print("built", flush=True)
driver = nonebot.get_driver()
assert str(driver.config.host) == "127.0.0.1"
with TestClient(driver.server_app) as client:
    health = client.get("/qqbotai/health").json()
    assert health["service"] == "qqbotai" and health["connected"] is False and health["groups_configured"] is True
    assert health["diagnostics"]["group_events"] == 0
    print("lifespan started", flush=True)
    try:
        with client.websocket_connect("/onebot/v11/", headers={"X-Self-ID": "10000"}):
            raise AssertionError("Missing token accepted")
    except WebSocketDisconnect:
        pass
    print("missing token rejected", flush=True)
    with client.websocket_connect("/onebot/v11/", headers={
            "X-Self-ID": "10000", "Authorization": "Bearer 0123456789abcdef"}) as ws:
        print("authorized websocket connected", flush=True)
        health = client.get("/qqbotai/health").json()
        assert health["connected"] is True
        assert "10000" not in str(health)
        ws.send_json({"time": 0, "self_id": 10000, "post_type": "message", "message_type": "group",
                      "sub_type": "normal", "user_id": 30000, "group_id": 20000, "message_id": 1,
                      "message": [{"type": "at", "data": {"qq": "10000"}},
                                  {"type": "text", "data": {"text": "/ping"}}],
                      "raw_message": "/ping", "font": 0, "sender": {"user_id": 30000}})
        result = ws.receive_json()
        print("reply received", flush=True)
        assert result["action"] in ("send_msg", "send_group_msg"), result["action"]
        assert result["params"]["group_id"] == 20000
        assert "我在线" in str(result["params"]["message"])
        ws.send_json({"status": "ok", "retcode": 0, "echo": result["echo"], "data": {"message_id": 2}})
        counts = client.get("/qqbotai/health").json()["diagnostics"]
        assert counts["group_events"] == 1 and counts["mentioned_events"] == 1
print("OneBot transport check passed")
'''
        environment = {k: v for k, v in os.environ.items() if not k.startswith(
            ("QQ_", "LLM_", "DEEPSEEK_", "ONEBOT_", "NAPCAT_", "VISION_", "SERPAPI_"))}
        with tempfile.TemporaryDirectory() as folder:
            try:
                result = subprocess.run([sys.executable, "-B", "-X", "utf8", "-c", program, str(root)],
                                        cwd=folder, env=environment, capture_output=True, timeout=20)
            except subprocess.TimeoutExpired as error:
                self.fail("Transport check timed out: " + (error.stdout or b"").decode("utf-8", errors="replace")[-2000:])
        self.assertEqual(result.returncode, 0, result.stderr.decode("utf-8", errors="replace")[-2000:])
        self.assertIn(b"OneBot transport check passed", result.stdout)
