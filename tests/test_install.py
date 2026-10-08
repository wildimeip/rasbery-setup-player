import io

import pytest

from pisetup.__main__ import main
from pisetup.system import Result
from tests.conftest import USB_CARD

APP = "opt/discord-player"


@pytest.fixture(autouse=True)
def sudo_user(monkeypatch):
    monkeypatch.setenv("SUDO_USER", "pi")


def env_of(pi):
    return (pi.root / APP / ".env").read_text()


def test_fresh_install(pi, runner, capsys):
    assert main([], pi) == 0
    out = capsys.readouterr().out
    r = pi.root
    for f in ["docker-compose.yml", ".env", ".env.example", "secrets/discord_token"]:
        assert (r / APP / f).is_file(), f
    for unit in [
        "discord-player.service",
        "discord-player-update.service",
        "discord-player-update.timer",
    ]:
        assert (r / "etc/systemd/system" / unit).is_file()
    env = env_of(pi)
    assert "MPV_AUDIO_DEVICE=alsa/plughw:CARD=Headphones,DEV=0" in env
    assert "AUDIO_GID=29" in env
    assert oct((r / APP / ".env").stat().st_mode)[-3:] == "600"
    assert oct((r / APP / "secrets/discord_token").stat().st_mode)[-3:] == "600"
    assert oct((r / APP / "secrets").stat().st_mode)[-3:] == "700"
    config = (r / "boot/firmware/config.txt").read_text()
    assert config == "dtparam=i2c_arm=on\ndtparam=audio=on\n"
    cmdline = (r / "boot/firmware/cmdline.txt").read_text()
    assert cmdline == "console=tty1 root=PARTUUID=1 rootwait cgroup_enable=memory cgroup_memory=1\n"
    assert "SystemMaxUse=50M" in (r / "etc/systemd/journald.conf.d/10-sdcard.conf").read_text()
    assert (
        "wifi.powersave = 2"
        in (r / "etc/NetworkManager/conf.d/99-wifi-powersave-off.conf").read_text()
    )
    assert "max-size" in (r / "etc/docker/daemon.json").read_text()
    assert runner.ran("apt-get", "upgrade")
    assert runner.ran("sh", "-c", "curl -fsSL https://get.docker.com | sh")
    assert runner.ran("usermod", "-aG", "docker", "pi")
    assert runner.ran("usermod", "-aG", "audio", "pi")
    assert runner.ran("amixer", "-q", "-c", "Headphones", "sset", "PCM", "100%", "unmute")
    assert runner.ran("systemctl", "enable", "discord-player.service")
    assert runner.ran("systemctl", "enable", "--now", "discord-player-update.timer")
    assert runner.ran("chown", "1000:1000", str(r / APP / "data"))
    # No token yet: not started; told what to do.
    assert not runner.ran("docker", "compose", "pull", "-q")
    assert "Paste the Discord bot token" in out and "Reboot once" in out


def test_rerun_keeps_settings_and_token(pi, runner, capsys):
    main([], pi)
    capsys.readouterr()
    assert "Reboot once" in _rerun_output(pi, capsys)  # still pending until a reboot
    (pi.root / "run/pisetup-reboot-required").unlink()  # rebooted
    env_file = pi.root / APP / ".env"
    env_file.write_text(env_file.read_text() + "CUSTOM=1\n")
    (pi.root / APP / "secrets/discord_token").write_text("tok\n")
    runner.calls.clear()
    runner.cwds.clear()
    runner.responses[("sh", "-c", "command -v docker")] = Result(0)
    assert main(["--no-upgrade", "--volume", "40"], pi) == 0
    out = capsys.readouterr().out
    env = env_of(pi)
    assert "CUSTOM=1" in env and "VOLUME=40" in env
    assert (pi.root / APP / "secrets/discord_token").read_text() == "tok\n"
    assert not runner.ran("apt-get", "upgrade")
    assert not runner.ran("sh", "-c", "curl -fsSL https://get.docker.com | sh")
    assert "Onboard audio already on" in out and "memory limits already on" in out
    # Token present: image pulled and player (re)started.
    assert runner.ran("docker", "compose", "pull", "-q")
    assert runner.cwds[runner.calls.index(("docker", "compose", "pull", "-q"))].endswith(APP)
    assert runner.ran("systemctl", "restart", "discord-player.service")
    assert "Reboot once" not in out and "Paste the Discord" not in out


def test_token_from_stdin_and_options(pi, runner, monkeypatch):
    monkeypatch.setattr("sys.stdin", io.StringIO("my-token\n"))
    (pi.root / "proc/asound/cards").write_text(
        (pi.root / "proc/asound/cards").read_text() + USB_CARD
    )
    args = ["--token-stdin", "--channel", "#tunes", "--audio", "auto"]
    assert main(args, pi) == 0
    assert (pi.root / APP / "secrets/discord_token").read_text() == "my-token\n"
    env = env_of(pi)
    assert "DISCORD_CHANNEL_NAME=tunes" in env
    assert "MPV_AUDIO_DEVICE=alsa/plughw:CARD=Device,DEV=0" in env
    assert runner.ran("systemctl", "restart", "discord-player.service")
    main(["--channel", "123, 456", "--audio", "hdmi", "--no-upgrade"], pi)
    env = env_of(pi)
    assert "DISCORD_CHANNEL_IDS=123,456" in env
    assert "MPV_AUDIO_DEVICE=alsa/hdmi:CARD=vc4hdmi,DEV=0" in env


def test_private_image_is_explained(pi, runner, capsys, monkeypatch):
    monkeypatch.setattr("sys.stdin", io.StringIO("tok\n"))
    runner.responses[("docker", "compose", "pull")] = Result(1)
    assert main(["--token-stdin"], pi) == 0
    assert "docker login ghcr.io" in capsys.readouterr().err


def test_refuses_wrong_setups(pi, runner, monkeypatch, capsys):
    runner.responses[("uname", "-m")] = Result(0, "armv7l\n")
    assert main([], pi) == 1
    assert "64-bit" in capsys.readouterr().err
    monkeypatch.delenv("SUDO_USER")
    assert main([], pi) == 1
    with pytest.raises(SystemExit):
        main(["--bogus"], pi)
    monkeypatch.setenv("SUDO_USER", "pi")
    runner.responses[("uname", "-m")] = Result(0, "aarch64\n")
    assert main(["--audio", "usb"], pi) == 1  # no USB card plugged in
    assert "No USB sound card" in capsys.readouterr().err


def test_failed_command_stops_setup(pi, runner, capsys):
    runner.responses[("apt-get", "update")] = Result(100)
    assert main([], pi) == 1
    assert "Setup stopped: Command failed (100): apt-get update -q" in capsys.readouterr().err


def _rerun_output(pi, capsys):
    main(["--no-upgrade"], pi)
    return capsys.readouterr().out
