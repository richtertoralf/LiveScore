"""Installer-only validation and first seed; normal server starts never seed."""
import argparse
from contextlib import ExitStack
import json
from pathlib import Path
import sys

import yaml

from .auth import Credentials
from .catalog import Selection, save_selection
from .config import load_config
from .models import State
from .storage import FileLease, load, save


def inspect_config(path):
    config = load_config(path)
    if config.auth.file.exists():
        # Read-only validation: do not initialize/reset accounts in an upgrade check.
        Credentials.model_validate(yaml.safe_load(config.auth.file.read_text()))
    for event in (config.data_dir / 'events').glob('*.json'):
        load(event)
    legacy = config.data_file or config.data_dir / 'tournament.json'
    if legacy.exists():
        load(legacy)
    selection = config.data_dir / 'active-event.json'
    if selection.exists():
        chosen = Selection.model_validate_json(selection.read_text())
        if chosen.active_event_id and not (config.data_dir / 'events' / f'{chosen.active_event_id}.json').is_file():
            raise ValueError('Aktive Veranstaltung fehlt.')
    return config


def seed_if_empty(config_path, source):
    config = inspect_config(config_path)
    state = State.model_validate_json(source.read_text(encoding='utf-8'))
    if state.event is None:
        raise ValueError('Seed enthält keine Veranstaltung.')
    directory = config.data_dir
    with ExitStack() as stack:
        for path in (directory / 'active-event.json', config.data_file or directory / 'tournament.json'):
            lease = FileLease(path)
            lease.acquire()
            stack.callback(lease.release)
        # Even an empty saved catalog or unknown file is existing runtime data.
        if any(p.is_file() and not p.name.endswith('.lock') for p in directory.rglob('*')):
            return False
        target = directory / 'events' / f'{source.stem}.json'
        selection = directory / 'active-event.json'
        # Selection validates the filename before any write.
        chosen = Selection(active_event_id=source.stem)
        save(target, state)
        try:
            save_selection(selection, chosen)
        except BaseException:
            target.unlink()
            raise
        return True


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', required=True, type=Path)
    parser.add_argument('--seed', type=Path)
    args = parser.parse_args()
    try:
        if args.seed:
            print('Prag vorbereitet.' if seed_if_empty(args.config, args.seed) else 'Vorhandene Daten unverändert.')
        else:
            config = inspect_config(args.config)
            print(json.dumps(dict(bind_host=config.bind_host, port=config.port,
                                 data_dir=str(config.data_dir), auth_file=str(config.auth.file),
                                 auth_enabled=config.auth.enabled)))
    except (ValueError, OSError, RuntimeError, yaml.YAMLError):
        print('Config/Auth/Veranstaltungsdaten ungültig oder gesperrt; unverändert abgebrochen.', file=sys.stderr)
        raise SystemExit(1)


if __name__ == '__main__':
    main()
