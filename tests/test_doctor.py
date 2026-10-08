import pytest

from pisetup.__main__ import main
from pisetup.system import Result


@pytest.fixture
def installed(pi, monkeypatch):
    monkeypatch.setenv("SUDO_USER", "pi")
    main(["--no-upgrade"], pi)
    return pi


def test_doctor_reports_what_to_fix(installed, runner, capsys):
    runner.responses[("vcgencmd",)] = Result(0, "throttled=0x50005\n")
    runner.responses[("docker", "inspect")] = Result(1)
    assert main(["doctor"], installed) == 1
    out = capsys.readouterr().out
    assert "OK    64-bit OS" in out
    assert "under-voltage" in out
    assert "no Discord bot token" in out
    assert "the player is not started" in out
    assert "sound card Headphones" in out


def test_doctor_all_good(installed, runner, capsys):
    (installed.root / "opt/discord-player/secrets/discord_token").write_text("t\n")
    runner.responses[("vcgencmd",)] = Result(0, "throttled=0x0\n")
    runner.responses[("docker", "inspect")] = Result(0, "running healthy\n")
    runner.responses[("docker", "logs")] = Result(0, "Logged in as bot; listening in ['#music']\n")
    assert main(["doctor"], installed) == 0
    out = capsys.readouterr().out
    assert "the player is running / healthy" in out
    assert "listening in ['#music']" in out
    assert out.strip().endswith("All good.")


def test_doctor_wrong_audio_device(installed, runner, capsys):
    env = installed.root / "opt/discord-player/.env"
    env.write_text(env.read_text().replace("CARD=Headphones", "CARD=Gone"))
    main(["doctor"], installed)
    assert "matches no sound card" in capsys.readouterr().out


def test_doctor_not_installed(pi, capsys):
    assert main(["doctor"], pi) == 1
    assert "not installed" in capsys.readouterr().out


def test_test_sound_frees_the_card(installed, runner):
    runner.calls.clear()
    assert main(["test-sound"], installed) == 0
    assert runner.calls[-3:] == [
        ("docker", "stop", "discord-player"),
        ("speaker-test", "-c", "2", "-t", "wav", "-l", "1", "-D", "plughw:CARD=Headphones,DEV=0"),
        ("docker", "start", "discord-player"),
    ]
