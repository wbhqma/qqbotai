"""只在本机同步独立 NapCat 运行目录的连接配置。"""

import json
import os
from pathlib import Path
import re
import secrets
import shutil

from dotenv import load_dotenv

from app.config import napcat_connection

DEFAULT_WORKDIR = Path(r"D:\IDE\NapCat\qqbotai-data")
CLIENT_NAME = "qqbotai-local"


def load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        raise ValueError("NapCat 配置文件不可读取。") from None
    if not isinstance(value, dict):
        raise ValueError("NapCat 配置须为 JSON 对象。")
    return value


def merge_client(config: dict, token: str, port: int) -> dict:
    result = dict(config)
    network = dict(result.get("network", {}))
    clients = network.get("websocketClients", [])
    if not isinstance(clients, list) or any(not isinstance(c, dict) for c in clients):
        raise ValueError("NapCat 客户端配置格式无效。")
    network["websocketClients"] = [c for c in clients if c.get("name") != CLIENT_NAME] + [{
        "name": CLIENT_NAME, "enable": True,
        "url": f"ws://127.0.0.1:{port}/onebot/v11/",
        "messagePostFormat": "array", "reportSelfMessage": False,
        "reconnectInterval": 5000, "heartInterval": 30000,
        "token": token, "debug": False, "verifyCertificate": True,
    }]
    for kind in ("httpServers", "httpSseServers", "httpClients", "websocketServers", "plugins"):
        network.setdefault(kind, [])
    result["network"] = network
    return result


def prepare(env_file: Path, workdir: Path = DEFAULT_WORKDIR) -> None:
    load_dotenv(env_file, override=False, encoding="utf-8")
    token, port = napcat_connection(os.environ)
    if len(token) < 16:
        raise ValueError("请先在本机配置 OneBot Token。")
    config_dir = workdir / "config"
    paths = [config_dir / "onebot11.json"]
    if config_dir.exists():
        paths.extend(p for p in config_dir.iterdir()
                     if re.fullmatch(r"onebot11_[0-9]+\.json", p.name) and p.is_file())
    # 先验证所有账号配置，避免遇到损坏文件时只更新一部分。
    changes = [(path, merge_client(load_json(path), token, port)) for path in paths]
    webui_path = config_dir / "webui.json"
    webui = load_json(webui_path)
    webui["host"] = "127.0.0.1"
    webui.setdefault("port", 6099)
    webui.setdefault("loginRate", 3)
    if not webui.get("token"):
        webui["token"] = secrets.token_urlsafe(32)
    changes.append((webui_path, webui))
    config_dir.mkdir(parents=True, exist_ok=True)
    for path, updated in changes:
        if path.exists() and load_json(path) == updated:
            continue
        if path.exists():
            backup = path.with_suffix(path.suffix + ".bak")
            if not backup.exists():
                shutil.copy2(path, backup)
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(json.dumps(updated, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        temporary.replace(path)
