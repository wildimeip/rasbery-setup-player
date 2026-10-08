import pytest

from pisetup.system import Result, System

PI_CARDS = """\
 0 [Headphones     ]: bcm2835_headpho - bcm2835 Headphones
                      bcm2835 Headphones
 1 [vc4hdmi        ]: vc4-hdmi - vc4-hdmi
                      vc4-hdmi
"""
USB_CARD = """\
 2 [Device         ]: USB-Audio - USB Audio Device
                      C-Media Electronics Inc. USB Audio Device at usb-3f980000.usb-1.3
"""


class FakeRunner:
    """Records commands; answers from `responses` (first matching command prefix wins)."""

    def __init__(self):
        self.calls: list[tuple[str, ...]] = []
        self.cwds: list[str | None] = []
        self.responses: dict[tuple[str, ...], Result] = {
            ("uname", "-m"): Result(0, "aarch64\n"),
            ("getent", "group", "audio"): Result(0, "audio:x:29:pi\n"),
            ("sh", "-c", "command -v docker"): Result(1),
        }

    def __call__(self, cmd, opts):
        cmd = tuple(cmd)
        self.calls.append(cmd)
        self.cwds.append(opts.get("cwd"))
        for prefix, result in self.responses.items():
            if cmd[: len(prefix)] == prefix:
                return result
        return Result(0, "")

    def ran(self, *prefix: str) -> bool:
        return any(c[: len(prefix)] == prefix for c in self.calls)


@pytest.fixture
def runner():
    return FakeRunner()


@pytest.fixture
def pi(tmp_path, runner):
    """A fresh Raspberry Pi OS Lite, as files under tmp_path."""
    root = tmp_path / "root"
    (root / "boot/firmware").mkdir(parents=True)
    (root / "boot/firmware/config.txt").write_text("dtparam=i2c_arm=on\n#dtparam=audio=on\n")
    (root / "boot/firmware/cmdline.txt").write_text("console=tty1 root=PARTUUID=1 rootwait\n")
    (root / "proc/asound").mkdir(parents=True)
    (root / "proc/asound/cards").write_text(PI_CARDS)
    (root / "proc/meminfo").write_text("MemTotal:         921000 kB\n")
    (root / "etc/NetworkManager").mkdir(parents=True)
    return System(root, runner)
