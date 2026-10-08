"""Prepares Raspberry Pi OS Lite: updates, Docker, SD card care, memory limits, Wi-Fi."""

from __future__ import annotations

import re

from .system import System

PACKAGES = [
    "unattended-upgrades",  # automatic security updates
    "curl",
    "git",
    "ca-certificates",
    "alsa-utils",  # aplay, amixer, speaker-test
]


def update_system(sys: System, upgrade: bool) -> None:
    sys.run("apt-get", "update", "-q")
    if upgrade:
        sys.run("apt-get", "upgrade", "-y", "-q")
    sys.run("apt-get", "install", "-y", "-q", *PACKAGES)
    # Security updates install themselves every day.
    sys.write(
        "/etc/apt/apt.conf.d/20auto-upgrades",
        'APT::Periodic::Update-Package-Lists "1";\nAPT::Periodic::Unattended-Upgrade "1";\n',
    )


def limit_logs(sys: System) -> None:
    """Fewer log writes: SD cards wear out."""
    changed = sys.write(
        "/etc/systemd/journald.conf.d/10-sdcard.conf", "[Journal]\nSystemMaxUse=50M\n"
    )
    if changed:
        sys.run("systemctl", "restart", "systemd-journald")


def install_docker(sys: System, user: str) -> None:
    if not sys.has_command("docker"):
        sys.run("sh", "-c", "curl -fsSL https://get.docker.com | sh")
    sys.run("usermod", "-aG", "docker", user)
    sys.run("systemctl", "enable", "--now", "docker")
    # Container logs rotate instead of filling the SD card.
    daemon = "/etc/docker/daemon.json"
    if not sys.exists(daemon):
        sys.write(
            daemon,
            '{\n  "log-driver": "json-file",\n'
            '  "log-opts": {"max-size": "10m", "max-file": "3"}\n}\n',
        )
        sys.run("systemctl", "restart", "docker")


def enable_memory_cgroup(sys: System) -> bool:
    """Pi OS ships with the memory cgroup off, so Docker ignores mem_limit.

    Returns True when a reboot is needed."""
    cmdline = next(
        (p for p in ("/boot/firmware/cmdline.txt", "/boot/cmdline.txt") if sys.exists(p)), None
    )
    if cmdline is None:
        print("No cmdline.txt found; skipped.")
        return False
    text = sys.read(cmdline)
    if "cgroup_memory=1" in text:
        print("Container memory limits already on.")
        return False
    sys.write(cmdline + ".bak", text)
    # cmdline.txt must stay one single line
    first, *rest = text.split("\n", 1)
    sys.write(cmdline, "\n".join([first.rstrip() + " cgroup_enable=memory cgroup_memory=1", *rest]))
    print(f"Turned on container memory limits in {cmdline} (backup: {cmdline}.bak).")
    return True


def wifi_power_save_off(sys: System) -> None:
    """The Pi 3B's Wi-Fi power saving causes dropouts in streamed music."""
    if not sys.exists("/etc/NetworkManager"):
        print("NetworkManager not in use; skipped.")
        return
    changed = sys.write(
        "/etc/NetworkManager/conf.d/99-wifi-powersave-off.conf",
        "[connection]\n# 2 = disabled\nwifi.powersave = 2\n",
    )
    if changed:
        sys.run("systemctl", "reload", "NetworkManager", check=False)


def memory_mb(sys: System) -> int | None:
    m = re.search(r"^MemTotal:\s+(\d+) kB", sys.read("/proc/meminfo"), re.M)
    return int(m.group(1)) // 1024 if m else None
