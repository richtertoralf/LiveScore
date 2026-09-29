import argparse
from pathlib import Path
import sys

import uvicorn

from . import __version__
from .app import create_app
from .config import ROOT, load_config


def main():
    parser = argparse.ArgumentParser(description="LiveScore – lokale Live-Spielstände")
    parser.add_argument("--version", action="version", version=f"LiveScore {__version__}")
    parser.add_argument("--reset-admin-password", action="store_true",
                        help="Admin-Passwort interaktiv setzen und Auth ohne Neustart neu laden")
    parser.add_argument("--config", type=Path, default=ROOT / "config/livescore.yml")
    if any(arg.startswith('--reset-admin-password=') for arg in sys.argv[1:]):
        parser.error('Passwort nur interaktiv eingeben; --reset-admin-password hat keinen Wert.')
    args, unknown = parser.parse_known_args()
    if unknown:
        parser.error('Unbekannte Argumente. Passwörter ausschließlich interaktiv eingeben.')
    config = load_config(args.config)
    if args.reset_admin_password:
        from .recovery import reset_admin_password
        raise SystemExit(reset_admin_password(args.config, config))
    uvicorn.run(create_app(config.data_file, data_dir=config.data_dir, auth_config=config.auth), host=config.bind_host, port=config.port, workers=1, proxy_headers=False)


if __name__ == "__main__":
    main()
