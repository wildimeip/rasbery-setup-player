"""Sound output: turns on the Pi's onboard audio and picks the device the player uses."""

from __future__ import annotations

import re
from dataclasses import dataclass

from .system import System

# " 0 [Headphones     ]: bcm2835_headpho - bcm2835 Headphones"
_CARD_LINE = re.compile(r"^\s*\d+\s+\[(\S+)\s*\]:\s*(.*?)\s+-\s+(.*)$")

JACK = "alsa/plughw:CARD=Headphones,DEV=0"
HDMI = "alsa/hdmi:CARD=vc4hdmi,DEV=0"
OUTPUTS = ("auto", "jack", "hdmi", "usb")


@dataclass(frozen=True)
class Card:
    id: str  # ALSA card id, e.g. Headphones, vc4hdmi, Device
    driver: str
    name: str

    @property
    def is_usb(self) -> bool:
        return "usb" in self.driver.lower() or "usb" in self.name.lower()

    @property
    def is_hdmi(self) -> bool:
        return "hdmi" in self.id.lower()


def sound_cards(sys: System) -> list[Card]:
    cards = []
    for line in sys.read("/proc/asound/cards").splitlines():
        m = _CARD_LINE.match(line)
        if m:
            cards.append(Card(*m.groups()))
    return cards


def device_for(output: str, cards: list[Card]) -> tuple[str, str]:
    """(mpv audio device, description) for jack / hdmi / usb / auto."""
    usb = next((c for c in cards if c.is_usb), None)
    if output == "usb" or (output == "auto" and usb):
        if usb is None:
            raise ValueError("No USB sound card found (plug it in, then run setup again)")
        return f"alsa/plughw:CARD={usb.id},DEV=0", f"USB sound card ({usb.name})"
    has_jack = any(c.id == "Headphones" for c in cards)
    hdmi = next((c for c in cards if c.is_hdmi), None)
    if output == "hdmi" or (output == "auto" and hdmi and not has_jack):
        card = hdmi.id if hdmi else "vc4hdmi"
        return f"alsa/hdmi:CARD={card},DEV=0", "HDMI"
    return JACK, "3.5 mm headphone jack"


def enable_onboard_audio(sys: System) -> bool:
    """dtparam=audio=on in config.txt. Returns True when a reboot is needed."""
    config = next(
        (p for p in ("/boot/firmware/config.txt", "/boot/config.txt") if sys.exists(p)), None
    )
    if config is None:
        print("No config.txt found; skipped.")
        return False
    text = sys.read(config)
    if re.search(r"^dtparam=audio=on\s*$", text, re.M):
        print("Onboard audio already on.")
        return False
    sys.write(config + ".bak", text)
    pattern = re.compile(r"^#?[ \t]*dtparam=audio=.*$", re.M)
    if pattern.search(text):
        text = pattern.sub("dtparam=audio=on", text, count=1)
    else:
        text = text.rstrip("\n") + "\ndtparam=audio=on\n"
    sys.write(config, text)
    print(f"Turned on onboard audio in {config} (backup: {config}.bak).")
    return True


def set_full_volume(sys: System, cards: list[Card]) -> None:
    """Hardware volume to 100% on every card: the player's own volume (!volume) does the rest."""
    for card in cards:
        for control in ("PCM", "Speaker", "Master", "Headphone"):
            if sys.run("amixer", "-c", card.id, "sget", control, check=False, capture=True).ok:
                sys.run("amixer", "-q", "-c", card.id, "sset", control, "100%", "unmute")
                break
    if cards:
        sys.run("alsactl", "store", check=False)
