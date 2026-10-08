"""Sets up a Raspberry Pi for the Discord music player.

sudo python3 -m pisetup                 install / update everything (safe to run again)
python3 -m pisetup doctor               check that everything works
sudo python3 -m pisetup test-sound      play a test sound on the configured output
"""

from __future__ import annotations

import argparse
import getpass
import os
import sys as _sys

from . import audio, doctor, player, prepare
from .system import CommandFailed, System

REBOOT_MARKER = "/run/pisetup-reboot-required"


def step(text: str) -> None:
    print(f"\n==> {text}", flush=True)


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="python3 -m pisetup", description=__doc__.split("\n")[0])
    p.add_argument(
        "command", nargs="?", default="install", choices=["install", "doctor", "test-sound"]
    )
    p.add_argument("--no-upgrade", action="store_true", help="skip the apt upgrade (quick re-run)")
    p.add_argument(
        "--audio",
        choices=audio.OUTPUTS,
        help="sound output: auto (USB card, else jack, else HDMI), jack, hdmi or usb",
    )
    p.add_argument("--channel", help="Discord channel name (music) or channel id(s): 123,456")
    p.add_argument("--volume", type=int, choices=range(0, 131), metavar="0-130")
    p.add_argument("--token-stdin", action="store_true", help="read the bot token from stdin")
    p.add_argument("--no-start", action="store_true", help="install, but don't start the player")
    return p.parse_args(argv)


def requested_settings(args: argparse.Namespace, sys: System, new_env: bool) -> dict[str, str]:
    """.env values to write: the options given, plus detected values for a new .env."""
    settings: dict[str, str] = {}
    if new_env:
        gid = sys.run("getent", "group", "audio", capture=True, check=False).stdout
        if gid.count(":") >= 2:
            settings["AUDIO_GID"] = gid.split(":")[2]
    if args.audio or new_env:
        device, description = audio.device_for(args.audio or "auto", audio.sound_cards(sys))
        settings["MPV_AUDIO_DEVICE"] = device
        print(f"Sound output: {description} ({device})")
    if args.channel:
        channel = args.channel.strip().lstrip("#")
        if channel.replace(",", "").replace(" ", "").isdigit():
            settings["DISCORD_CHANNEL_IDS"] = channel.replace(" ", "")
        else:
            settings["DISCORD_CHANNEL_IDS"] = ""
            settings["DISCORD_CHANNEL_NAME"] = channel
    if args.volume is not None:
        settings["VOLUME"] = str(args.volume)
    return settings


def install(args: argparse.Namespace, sys: System, user: str) -> int:
    arch = sys.run("uname", "-m", capture=True).stdout.strip()
    if arch != "aarch64":
        print(f"This needs 64-bit Raspberry Pi OS (aarch64); found {arch}.", file=_sys.stderr)
        return 1
    reboot = False

    step("Updating the system and turning on automatic security updates")
    prepare.update_system(sys, upgrade=not args.no_upgrade)
    step("Limiting log writes to protect the SD card")
    prepare.limit_logs(sys)
    step("Installing Docker")
    prepare.install_docker(sys, user)
    step("Turning on container memory limits")
    reboot |= prepare.enable_memory_cgroup(sys)
    step("Turning off Wi-Fi power saving (avoids music dropouts)")
    prepare.wifi_power_save_off(sys)

    step("Setting up sound")
    sys.run("usermod", "-aG", "audio", user)
    reboot |= audio.enable_onboard_audio(sys)
    cards = audio.sound_cards(sys)
    audio.set_full_volume(sys, cards)
    for card in cards:
        print(f"Sound card: {card.id} ({card.name})")
    if not cards:
        print("No sound cards visible yet (normal before the first reboot).")

    # /run is emptied by a reboot, so this marker remembers a pending reboot between re-runs.
    if reboot:
        sys.write(REBOOT_MARKER, "")
    reboot = sys.exists(REBOOT_MARKER)

    step(f"Installing the player in {player.APP_DIR}")
    new_env = not sys.exists(f"{player.APP_DIR}/.env")
    settings = requested_settings(args, sys, new_env)
    player.install_files(sys, user, settings)
    if args.token_stdin:
        token = _sys.stdin.readline().strip()
        if token:
            player.save_token(sys, token)
    elif not player.has_token(sys) and _sys.stdin.isatty():
        token = getpass.getpass("Paste the Discord bot token (input hidden, Enter to skip): ")
        if token.strip():
            player.save_token(sys, token)
    player.install_units(sys)

    started = False
    if player.has_token(sys) and not args.no_start:
        step("Starting the player")
        started = player.start(sys)
        if not started:
            print(
                "Could not download the image. If the GitHub package is private, run "
                "'docker login ghcr.io' (or make the package public), then run setup again.",
                file=_sys.stderr,
            )

    print("\nDone.")
    steps = []
    if not player.has_token(sys):
        steps.append(f"Paste the Discord bot token: sudo nano {player.TOKEN}")
    steps.append(f"Check the settings: nano {player.APP_DIR}/.env (channel, volume, sound output)")
    if reboot:
        steps.append(
            "Reboot once (sudo reboot): turns on sound and memory limits; "
            "the player then starts by itself"
        )
    elif not started:
        steps.append("Start: sudo systemctl restart discord-player")
    steps.append("Check everything: python3 -m pisetup doctor")
    steps.append(f"Log out and back in so '{user}' can use docker without sudo")
    for i, text in enumerate(steps, 1):
        print(f"  {i}. {text}")
    return 0


def test_sound(sys: System) -> int:
    env = sys.read(f"{player.APP_DIR}/.env")
    device = (player.get_env(env, "MPV_AUDIO_DEVICE") or "").removeprefix("alsa/") or "default"
    running = sys.run("docker", "inspect", doctor.CONTAINER, capture=True, check=False).ok
    if running:  # the player holds the sound card
        sys.run("docker", "stop", doctor.CONTAINER, check=False)
    print(f"Playing 'front left, front right' on {device} ...")
    result = sys.run("speaker-test", "-c", "2", "-t", "wav", "-l", "1", "-D", device, check=False)
    if running:
        sys.run("docker", "start", doctor.CONTAINER, check=False)
    if not result.ok:
        print("No sound played. Try: python3 -m pisetup doctor", file=_sys.stderr)
    return 0 if result.ok else 1


def main(argv: list[str] | None = None, sys: System | None = None) -> int:
    args = parse_args(argv)
    sys = sys or System()
    if args.command == "doctor":
        return doctor.check(sys)
    if os.geteuid() != 0 and sys.root.as_posix() == "/":
        print(f"Run with sudo: sudo python3 -m pisetup {args.command}", file=_sys.stderr)
        return 1
    if args.command == "test-sound":
        return test_sound(sys)
    user = os.environ.get("SUDO_USER", "")
    if not user or user == "root":
        print("Run as your normal user with sudo (not as root directly).", file=_sys.stderr)
        return 1
    try:
        return install(args, sys, user)
    except (CommandFailed, ValueError) as e:
        print(f"\nSetup stopped: {e}", file=_sys.stderr)
        return 1


if __name__ == "__main__":
    _sys.exit(main())
