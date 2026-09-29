"""Atomare JSON-Persistenz und exklusive Prozesssperre für eine Datendatei."""
import os
from pathlib import Path
import tempfile

from .models import State


def load(path: Path) -> State:
    if not path.exists():
        return State()
    return State.model_validate_json(path.read_text(encoding="utf-8"))


def save(path: Path, state: State):
    validated = State.model_validate(state.model_dump())
    atomic_write(path, validated.model_dump_json(indent=2) + "\n")


def atomic_write(path: Path, text: str):
    """Der Aufrufer validiert den Inhalt und hält die zugehörige Schreibsperre."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                         prefix=f".{path.name}.", suffix=".tmp", delete=False) as file:
            temporary = Path(file.name)
            file.write(text)
            file.flush()
            os.fsync(file.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


class FileLease:
    """OS-Sperre bleibt bis zum Shutdown gehalten; Abstürze geben sie frei."""
    def __init__(self, path: Path):
        self.path = path.with_suffix(path.suffix + ".lock")
        self.file = None

    def acquire(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        file = self.path.open("a+b")
        try:
            if os.name == "nt":
                import msvcrt
                file.seek(0, 2)
                if file.tell() == 0:
                    file.write(b"\0")
                    file.flush()
                file.seek(0)
                msvcrt.locking(file.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            file.close()
            raise RuntimeError("Datendatei bereits in Verwendung. Nur einen LiveScore-Prozess starten.") from exc
        self.file = file

    def release(self):
        if self.file:
            self.file.close()
            self.file = None
