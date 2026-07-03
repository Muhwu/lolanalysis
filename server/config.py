"""Project configuration loaded from a .env file in the project root."""
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


class ConfigError(Exception):
    pass


@dataclass
class Config:
    riot_api_key: str
    db_path: Path
    accounts: list


def parse_env_file(path: Path) -> dict:
    values = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value.strip().strip("'\"")
    return values


def parse_accounts(raw: str) -> list:
    accounts = []
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        if "#" not in part:
            raise ConfigError(f"Account {part!r} must be in Name#TAG format")
        name, _, tag = part.partition("#")
        accounts.append((name.strip(), tag.strip()))
    return accounts


def load_config(root: Path | None = None) -> Config:
    root = Path(root) if root else PROJECT_ROOT
    env_path = root / ".env"
    if not env_path.exists():
        raise ConfigError(
            f"No .env file at {env_path}. Run setup.sh or create one with RIOT_API_KEY=..."
        )
    env = parse_env_file(env_path)
    api_key = env.get("RIOT_API_KEY", "")
    if not api_key:
        raise ConfigError(f"RIOT_API_KEY missing from {env_path}")
    if not env.get("ACCOUNTS"):
        raise ConfigError(
            f"ACCOUNTS missing from {env_path}. "
            'Set it to a comma-separated list of Riot IDs, e.g. ACCOUNTS=Name#EUW, Other#EUW'
        )
    accounts = parse_accounts(env["ACCOUNTS"])
    db_path = Path(env["DB_PATH"]) if env.get("DB_PATH") else root / "data" / "lol.sqlite"
    return Config(riot_api_key=api_key, db_path=db_path, accounts=accounts)
