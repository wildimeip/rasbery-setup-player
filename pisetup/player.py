"""Installs the player to /opt/discord-player: compose file, .env, token secret, systemd units."""

from __future__ import annotations

import re
from pathlib import Path

from .system import System

APP_DIR = "/opt/discord-player"
APP_UID = 1000  # the user the app runs as inside the container
FILES = Path(__file__).parent / "files"
UNITS = ("discord-player.service", "discord-player-update.service", "discord-player-update.timer")
TOKEN = f"{APP_DIR}/secrets/discord_token"


def set_env(text: str, key: str, value: str) -> str:
    """Sets KEY=value in .env text (replacing the line, or adding one)."""
    line = f"{key}={value}"
    pattern = re.compile(rf"^#?[ \t]*{re.escape(key)}=.*$", re.M)
    if pattern.search(text):
        return pattern.sub(lambda _: line, text, count=1)
    return text.rstrip("\n") + f"\n{line}\n"


def get_env(text: str, key: str) -> str | None:
    m = re.search(rf"^{re.escape(key)}=(.*)$", text, re.M)
    return m.group(1).strip() if m else None


def install_files(sys: System, user: str, settings: dict[str, str]) -> bool:
    """Copies the files and writes .env. Existing .env, token and data are kept; only the
    settings passed (from command-line options) are changed. Returns True for a new .env."""
    sys.mkdir(APP_DIR)
    sys.copy(FILES / "docker-compose.yml", f"{APP_DIR}/docker-compose.yml")
    sys.copy(FILES / ".env.example", f"{APP_DIR}/.env.example")
    env_path = f"{APP_DIR}/.env"
    new = not sys.exists(env_path)
    text = sys.read(f"{APP_DIR}/.env.example") if new else sys.read(env_path)
    for key, value in settings.items():
        text = set_env(text, key, value)
    sys.write(env_path, text, mode=0o600)
    sys.mkdir(f"{APP_DIR}/data")
    sys.mkdir(f"{APP_DIR}/secrets", mode=0o700)
    if not sys.exists(TOKEN):
        sys.write(TOKEN, "")
    sys.path(TOKEN).chmod(0o600)
    sys.chown(f"{user}:", APP_DIR, env_path)
    sys.chown(f"{APP_UID}:{APP_UID}", f"{APP_DIR}/data")
    sys.chown(f"{APP_UID}:{APP_UID}", f"{APP_DIR}/secrets", recursive=True)
    return new


def has_token(sys: System) -> bool:
    return bool(sys.read(TOKEN).strip())


def save_token(sys: System, token: str) -> None:
    sys.write(TOKEN, token.strip() + "\n", mode=0o600)
    sys.chown(f"{APP_UID}:{APP_UID}", TOKEN)


def install_units(sys: System) -> None:
    for unit in UNITS:
        sys.copy(FILES / "systemd" / unit, f"/etc/systemd/system/{unit}")
    sys.run("systemctl", "daemon-reload")
    # Starts the player at boot; the timer pulls a new image (fresh yt-dlp) every night.
    sys.run("systemctl", "enable", "discord-player.service")
    sys.run("systemctl", "enable", "--now", "discord-player-update.timer")


def start(sys: System) -> bool:
    """Pulls the image and starts the player. False when the pull failed (private image)."""
    if not sys.run("docker", "compose", "pull", "-q", cwd=APP_DIR, check=False).ok:
        return False
    sys.run("systemctl", "restart", "discord-player.service")
    return True
