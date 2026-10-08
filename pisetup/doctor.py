"""`python3 -m pisetup doctor`: checks everything the player needs and says how to fix it."""

from __future__ import annotations

from .audio import sound_cards
from .player import APP_DIR, get_env, has_token
from .prepare import memory_mb
from .system import System

CONTAINER = "discord-player"


class Report:
    def __init__(self) -> None:
        self.failures = 0

    def ok(self, text: str) -> None:
        print(f"  OK    {text}")

    def bad(self, text: str, fix: str) -> None:
        self.failures += 1
        print(f"  FIX   {text}\n        -> {fix}")

    def info(self, text: str) -> None:
        print(f"  ..    {text}")


def check(sys: System) -> int:
    r = Report()
    print("Raspberry Pi")
    arch = sys.run("uname", "-m", capture=True, check=False).stdout.strip()
    if arch == "aarch64":
        r.ok("64-bit OS (aarch64)")
    else:
        r.bad(f"architecture is {arch}", "install Raspberry Pi OS Lite (64-bit)")
    mem = memory_mb(sys)
    if mem:
        r.info(f"{mem} MB memory")
    throttled = sys.run("vcgencmd", "get_throttled", capture=True, check=False)
    if throttled.ok:
        value = throttled.stdout.strip().partition("=")[2]
        if value in ("0x0", ""):
            r.ok("power supply is fine (not throttled)")
        else:
            r.bad(
                f"under-voltage or throttling reported ({value})",
                "use a 5.1 V / 2.5 A supply and a short, thick cable",
            )

    print("Docker")
    if sys.run("docker", "info", capture=True, check=False).ok:
        r.ok("Docker is running")
    else:
        r.bad("Docker is not running", "sudo systemctl start docker, or run setup again")

    print("Player")
    if not sys.exists(f"{APP_DIR}/.env"):
        r.bad("not installed", "sudo python3 -m pisetup")
        return _done(r)
    env = sys.read(f"{APP_DIR}/.env")
    if has_token(sys):
        r.ok("Discord bot token is set")
    else:
        r.bad("no Discord bot token", f"sudo nano {APP_DIR}/secrets/discord_token")
    ids = get_env(env, "DISCORD_CHANNEL_IDS")
    name = get_env(env, "DISCORD_CHANNEL_NAME") or "music"
    r.info(f"listens in channel ids {ids}" if ids else f"listens in channels named #{name}")
    timer = sys.run(
        "systemctl", "is-enabled", "discord-player-update.timer", capture=True, check=False
    )
    if timer.ok:
        r.ok("nightly updates are on")
    else:
        r.bad("nightly updates are off", "sudo systemctl enable --now discord-player-update.timer")

    print("Sound")
    cards = sound_cards(sys)
    for card in cards:
        r.info(f"sound card {card.id}: {card.name}")
    device = get_env(env, "MPV_AUDIO_DEVICE") or ""
    if not cards:
        r.bad("no sound cards", "reboot once after setup (it turns on the onboard audio)")
    elif device and not any(f"CARD={c.id}," in device for c in cards):
        r.bad(
            f"MPV_AUDIO_DEVICE={device} matches no sound card",
            "sudo python3 -m pisetup --audio auto (or jack / hdmi / usb)",
        )
    else:
        r.ok(f"sound output: {device or 'system default'}")

    print("Container")
    state = sys.run(
        "docker",
        "inspect",
        "-f",
        "{{.State.Status}} {{if .State.Health}}{{.State.Health.Status}}{{end}}",
        CONTAINER,
        capture=True,
        check=False,
    )
    status = state.stdout.split() if state.ok else []
    if not status:
        r.bad("the player is not started", f"cd {APP_DIR} && docker compose up -d")
    elif status[0] != "running":
        r.bad(f"the player is {status[0]}", f"cd {APP_DIR} && docker compose logs --tail 50")
    elif len(status) > 1 and status[1] == "unhealthy":
        r.bad("the player is running but not connected", f"cd {APP_DIR} && docker compose logs")
    else:
        r.ok(f"the player is {' / '.join(status)}")
    if status:
        logs = sys.run("docker", "logs", "--tail", "8", CONTAINER, capture=True, check=False)
        for line in logs.stdout.splitlines():
            r.info(f"log: {line}")
    return _done(r)


def _done(r: Report) -> int:
    print()
    print("All good." if not r.failures else f"{r.failures} thing(s) to fix, see above.")
    return 1 if r.failures else 0
