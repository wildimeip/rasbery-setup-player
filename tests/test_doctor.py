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
    assert "under-voltage, throttled right now (0x50005)" in out
    assert "no Discord bot token" in out
    assert "the player is not started" in out
    assert "sound card Headphones" in out


def test_doctor_all_good(installed, runner, capsys):
    (installed.root / "opt/discord-player/secrets/discord_token").write_text("t\n")
    runner.responses[("vcgencmd",)] = Result(0, "throttled=0x0\n")
    runner.responses[("docker", "inspect")] = Result(0, "running 0 healthy\n")
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


INTENT = "Turn on 'Message Content Intent' for the bot in the Discord Developer Portal\n"


@pytest.mark.parametrize("state", ["restarting 4 \n", "running 5 starting\n"])
def test_doctor_crash_loop_shows_the_fix(installed, runner, capsys, state):
    """First real run: the player restarted forever and doctor called it 'running'."""
    (installed.root / "opt/discord-player/secrets/discord_token").write_text("t\n")
    runner.responses[("docker", "inspect")] = Result(0, state)
    runner.responses[("docker", "logs")] = Result(0, "INFO start\n" + INTENT)
    assert main(["doctor"], installed) == 1
    out = capsys.readouterr().out
    assert "the player keeps restarting" in out
    assert "-> Discord: turn on Message Content Intent" in out
    assert "log: Turn on 'Message Content Intent'" in out


def test_doctor_just_started(installed, runner, capsys):
    (installed.root / "opt/discord-player/secrets/discord_token").write_text("t\n")
    runner.responses[("docker", "inspect")] = Result(0, "running 0 starting\n")
    assert main(["doctor"], installed) == 0
    assert "starting (run doctor again in a minute)" in capsys.readouterr().out


@pytest.mark.parametrize(
    "value, expected, failures",
    [
        ("0x50000", "under-voltage, throttling happened since boot (0x50000), fine now", 0),
        ("0x0", "power supply is fine", 0),
        ("0x1", "under-voltage right now (0x1)", 1),
    ],
)
def test_power(installed, runner, capsys, value, expected, failures):
    (installed.root / "opt/discord-player/secrets/discord_token").write_text("t\n")
    runner.responses[("docker", "inspect")] = Result(0, "running 0 healthy\n")
    runner.responses[("vcgencmd",)] = Result(0, f"throttled={value}\n")
    assert main(["doctor"], installed) == failures
    assert expected in capsys.readouterr().out
