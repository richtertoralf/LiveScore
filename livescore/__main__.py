import argparse
from pathlib import Path

import uvicorn

from . import __version__
from .app import create_app
from .config import ROOT, load_config


def main():
    parser = argparse.ArgumentParser(description="LiveScore – lokale Live-Spielstände")
    parser.add_argument("--version", action="version", version=f"LiveScore {__version__}")
    parser.add_argument("--config", type=Path, default=ROOT / "config/livescore.yml")
    args = parser.parse_args()
    config = load_config(args.config)
    uvicorn.run(create_app(config.data_file, data_dir=config.data_dir, auth_config=config.auth), host=config.bind_host, port=config.port, workers=1, proxy_headers=False)


if __name__ == "__main__":
    main()
