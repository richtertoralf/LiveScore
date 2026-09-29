from pathlib import Path

import yaml
from pydantic import Field, model_validator

from .models import Model, Text
from .auth import AuthConfig

ROOT = Path(__file__).resolve().parent.parent


class Config(Model):
    bind_host: Text
    port: int = Field(strict=True, ge=1, le=65535)
    data_dir: Path | None = None
    data_file: Path | None = None
    auth: AuthConfig = Field(default_factory=AuthConfig)

    @model_validator(mode="after")
    def location(self):
        if (self.data_dir is None) == (self.data_file is None):
            raise ValueError("Genau einen Datenpfad angeben: data_dir oder Legacy-data_file.")
        if self.data_file == Path("."):
            raise ValueError("data_file muss eine Datei bezeichnen.")
        return self


def load_config(path: Path) -> Config:
    path = path.resolve()
    config = Config.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
    config.auth.file = (path.parent / config.auth.file).resolve()
    if config.data_file is not None:
        config.data_file = (path.parent / config.data_file).resolve()
        config.data_dir = config.data_file.parent
    else:
        config.data_dir = (path.parent / config.data_dir).resolve()
    return config
