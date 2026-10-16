import argparse
from pathlib import Path

from app.config import ROOT
from app.napcat import DEFAULT_WORKDIR, prepare


def main() -> int:
    parser = argparse.ArgumentParser(description="同步 qqbotai 与本机 NapCat 的连接配置")
    parser.add_argument("--workdir", type=Path, default=DEFAULT_WORKDIR)
    args = parser.parse_args()
    try:
        prepare(ROOT / ".env", args.workdir)
    except (OSError, ValueError, TypeError):
        print("NapCat 配置未完成：请检查本机 Token、端口、目录权限和配置格式；具体值已隐藏。")
        return 2
    print("NapCat 本机连接配置已同步；WebUI 仅限本机访问，密钥与账号信息未输出。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
