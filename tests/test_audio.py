import pytest

from pisetup.audio import Card, device_for, enable_onboard_audio, sound_cards
from tests.conftest import PI_CARDS, USB_CARD

JACK = Card("Headphones", "bcm2835_headpho", "bcm2835 Headphones")
HDMI = Card("vc4hdmi", "vc4-hdmi", "vc4-hdmi")
USB = Card("Device", "USB-Audio", "USB Audio Device")


def test_parse_cards(pi):
    (pi.root / "proc/asound/cards").write_text(PI_CARDS + USB_CARD)
    assert sound_cards(pi) == [JACK, HDMI, USB]


@pytest.mark.parametrize(
    "output, cards, device",
    [
        ("auto", [JACK, HDMI], "alsa/plughw:CARD=Headphones,DEV=0"),
        ("auto", [JACK, HDMI, USB], "alsa/plughw:CARD=Device,DEV=0"),
        ("auto", [HDMI], "alsa/hdmi:CARD=vc4hdmi,DEV=0"),
        ("auto", [], "alsa/plughw:CARD=Headphones,DEV=0"),  # before the first reboot
        ("hdmi", [JACK, HDMI, USB], "alsa/hdmi:CARD=vc4hdmi,DEV=0"),
        ("jack", [JACK, USB], "alsa/plughw:CARD=Headphones,DEV=0"),
    ],
)
def test_device_for(output, cards, device):
    assert device_for(output, cards)[0] == device


def test_usb_required():
    with pytest.raises(ValueError):
        device_for("usb", [JACK])


@pytest.mark.parametrize(
    "before, after",
    [
        ("a=1\ndtparam=audio=off\n", "a=1\ndtparam=audio=on\n"),
        ("a=1\n# dtparam=audio=on\n", "a=1\ndtparam=audio=on\n"),
        ("a=1", "a=1\ndtparam=audio=on\n"),
    ],
)
def test_enable_onboard_audio(pi, before, after):
    config = pi.root / "boot/firmware/config.txt"
    config.write_text(before)
    assert enable_onboard_audio(pi)
    assert config.read_text() == after
    assert (pi.root / "boot/firmware/config.txt.bak").read_text() == before
    assert not enable_onboard_audio(pi)
