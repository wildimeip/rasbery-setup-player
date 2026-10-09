"""`python3 -m pisetup doctor`: checks everything the player needs and says how to fix it."""

from __future__ import annotations

from .audio import sound_cards
from .player import APP_DIR, get_env, has_token
from .prepare import memory_mb
from .system import System

CONTAINER = "discord-player"

# vcgencmd get_throttled bits: the low ones are "now", the 0x10000+ ones "since boot".
THROTTLE_NOW = {0x1: "under-voltage", 0x2: "CPU speed capped", 0x4: "throttled", 0x8: "too hot"}
THROTTLE_PAST = {0x10000: "under-voltage", 0x20000: "CPU speed capped", 0x40000: "throttling"}
THROTTLE_PAST[0x80000] = "overheating"

# Known reasons the player exits at start, and what fixes them.
KNOWN_ERRORS = {
    "Message Content Intent": (
        "Discord: turn on Message Content Intent (Developer Portal -> your app -> Bot -> "
        "Privileged Gateway Intents), save, then: sudo systemctl restart discord-player"
    ),
    "rejected the bot token": (
        f"put the right token in {APP_DIR}/secrets/discord_token (sudo nano), "
        "then: sudo systemctl restart discord-player"
    ),
    "No Discord bot token": f"sudo nano {APP_DIR}/secrets/discord_token",
    "Configuration error": f"fix the value named above in {APP_DIR}/.env",
}


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
        _check_power(r, throttled.stdout.strip().partition("=")[2])

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
        "{{.State.Status}} {{.RestartCount}} {{if .State.Health}}{{.State.Health.Status}}{{end}}",
        CONTAINER,
        capture=True,
        check=False,
    )
    fields = state.stdout.split() if state.ok else []
    if not fields:
        r.bad("the player is not started", f"cd {APP_DIR} && docker compose up -d")
        return _done(r)
    status = fields[0]
    restarts = int(fields[1]) if len(fields) > 1 and fields[1].isdigit() else 0
    health = fields[2] if len(fields) > 2 else ""
    logs = sys.run("docker", "logs", "--tail", "40", CONTAINER, capture=True, check=False).stdout
    known = next((fix for text, fix in KNOWN_ERRORS.items() if text in logs), None)
    logs_hint = f"cd {APP_DIR} && docker compose logs --tail 50"
    if status == "restarting" or restarts >= 3:
        r.bad(f"the player keeps restarting ({restarts} restarts)", known or logs_hint)
    elif status != "running":
        r.bad(f"the player is {status}", known or logs_hint)
    elif health == "unhealthy":
        r.bad("the player is running but not connected to Discord", known or logs_hint)
    elif health == "starting":
        r.info("the player is starting (run doctor again in a minute)")
    else:
        r.ok(f"the player is running{f' / {health}' if health else ''}")
    for line in logs.splitlines()[-8:]:
        r.info(f"log: {line}")
    return _done(r)


def _check_power(r: Report, value: str) -> None:
    try:
        bits = int(value, 16)
    except ValueError:
        return
    now = [name for bit, name in THROTTLE_NOW.items() if bits & bit]
    past = [name for bit, name in THROTTLE_PAST.items() if bits & bit]
    if now:
        r.bad(
            f"{', '.join(now)} right now ({value})",
            "use a 5.1 V / 2.5 A supply and a short, thick cable (and some airflow)",
        )
    elif past:
        r.info(
            f"{', '.join(past)} happened since boot ({value}), fine now. If it keeps "
            "happening during normal use, get a better power supply."
        )
    else:
        r.ok("power supply is fine")


def _done(r: Report) -> int:
    print()
    print("All good." if not r.failures else f"{r.failures} thing(s) to fix, see above.")
    return 1 if r.failures else 0
