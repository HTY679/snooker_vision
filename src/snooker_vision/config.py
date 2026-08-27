from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any, Mapping

import yaml


DEFAULT_CONFIG_PATH = Path(__file__).resolve().parents[2] / "config" / "default.yaml"


class ConfigError(RuntimeError):
    pass


def _deep_merge(base: dict[str, Any], override: Mapping[str, Any]) -> dict[str, Any]:
    result = deepcopy(base)
    for key, value in override.items():
        if isinstance(value, Mapping) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = deepcopy(value)
    return result


def _read_yaml(path: Path) -> dict[str, Any]:
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ConfigError(f"Configuration file not found: {path}") from exc
    except (OSError, yaml.YAMLError) as exc:
        raise ConfigError(f"Cannot load configuration {path}: {exc}") from exc
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise ConfigError(f"Configuration root must be a mapping: {path}")
    return raw


def load_config(path: str | Path | None = None) -> dict[str, Any]:
    base = _read_yaml(DEFAULT_CONFIG_PATH)
    if path is None:
        return base
    custom_path = Path(path)
    if custom_path.resolve() == DEFAULT_CONFIG_PATH.resolve():
        return base
    return _deep_merge(base, _read_yaml(custom_path))


def require_section(config: Mapping[str, Any], name: str) -> Mapping[str, Any]:
    section = config.get(name)
    if not isinstance(section, Mapping):
        raise ConfigError(f"Missing or invalid configuration section: {name}")
    return section

