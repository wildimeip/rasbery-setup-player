# rasbery-setup-player

Prepares a **Raspberry Pi 3B** (any 64-bit Pi works) to run the Discord music player,
**[rasbery-discord-player](https://github.com/wildimeip/rasbery-discord-player)**: songs posted in a
Discord channel are found on YouTube Music and played on speakers plugged into the Pi.

One command sets up everything and can be run again at any time:

```sh
sudo python3 -m pisetup
```

It uses only the Python that comes with Raspberry Pi OS (no packages to install) and:

- updates the system and turns on **automatic security updates**
- limits log writes and rotates container logs, to spare the **SD card**
- installs **Docker** and turns on container memory limits (Pi OS has them off)
- turns on the **onboard sound**, sets the hardware volume to 100% and picks the output:
  a USB sound card if one is plugged in, otherwise the 3.5 mm jack (or HDMI)
- turns off **Wi-Fi power saving**, which causes dropouts in streamed music on the Pi 3B
- installs the player to `/opt/discord-player` (compose file, settings, bot token as a secret)
- **starts the player at every boot** and **updates it every night** (new images bring a fresh
  yt-dlp, which keeps YouTube working)

## 1. Prepare the SD card (on your computer)

1. Install **Raspberry Pi Imager** from raspberrypi.com/software and insert the SD card
   (a good 16-32 GB, A1/A2 rated).
2. **Choose device:** Raspberry Pi 3. **Choose OS:** *Raspberry Pi OS (other)* ->
   **Raspberry Pi OS Lite (64-bit)**. **Choose storage:** the SD card.
3. **Next** -> **Edit settings**:
   - *General:* hostname (e.g. `musicpi`), username and password, Wi-Fi name and password,
     **Wi-Fi country**, time zone and keyboard layout.
   - *Services:* **Enable SSH** (public-key only is best).
4. Write the card, put it in the Pi, power on, wait a few minutes, then
   `ssh <username>@musicpi.local` (or use the Pi's IP address from your router).

Pi 3B notes: its Wi-Fi is **2.4 GHz only**; a network cable is more reliable. Use a
**5.1 V / 2.5 A** power supply: a weak one causes crashes and SD card corruption (the doctor
below checks for it).

## 2. Create the Discord bot (once)

1. https://discord.com/developers/applications -> **New Application**, give it a name.
2. **Bot** tab -> **Reset Token** -> copy the token. On the same tab switch on
   **Message Content Intent** and save.
3. **OAuth2** -> **URL Generator**: scope `bot`; permissions *View Channels*, *Send Messages*,
   *Read Message History*. Open the generated URL and add the bot to your server.
4. Create a text channel named `music` (or pick another one with `--channel`).

## 3. Install (on the Pi)

```sh
sudo apt-get update && sudo apt-get install -y git
git clone https://github.com/wildimeip/rasbery-setup-player.git ~/rasbery-setup-player
cd ~/rasbery-setup-player
sudo python3 -m pisetup
```

It asks for the bot token (paste it; nothing is shown while you type). When it finishes:

1. `sudo reboot` once (turns on the sound and memory limits). The player starts by itself.
2. `python3 -m pisetup doctor` checks everything and says how to fix what isn't right.
3. In Discord, write `!start` in `#music` for random music, or a song name to play it.

If the repository is private, sign in on the Pi first (`gh auth login`, or clone with a
personal access token). If the player's image is private, either make the
`rasbery-discord-player` package public on GitHub (your profile -> Packages -> Package
settings -> Change visibility) or run `docker login ghcr.io` on the Pi with a token that can
read packages.

### Options

| Option | What it does |
| --- | --- |
| `--audio auto\|jack\|hdmi\|usb` | sound output (default `auto`: USB card, else jack) |
| `--channel music` or `--channel 1234,5678` | channel name, or channel id(s), to listen in |
| `--volume 70` | start volume, 0-130 |
| `--token-stdin` | read the token from stdin: `echo "$TOKEN" \| sudo python3 -m pisetup --token-stdin` |
| `--no-upgrade` | skip the slow apt upgrade (quick re-run) |
| `--no-start` | install, but don't start the player |

Run it again any time, e.g. after a `git pull` or to switch the output to a USB sound card:
`sudo python3 -m pisetup --no-upgrade --audio usb`. Your settings, token and song history are
kept; only the options you pass change.

### Other commands

```sh
python3 -m pisetup doctor           # health check: power, Docker, token, sound, player status, logs
sudo python3 -m pisetup test-sound  # "front left, front right" on the configured output
```

## Where things are

| Path | What |
| --- | --- |
| `/opt/discord-player/.env` | settings (channel, sound output, volume, random mode, ...), explained in `.env.example` next to it |
| `/opt/discord-player/secrets/discord_token` | the bot token (readable only by the player), passed to it as a Docker secret |
| `/opt/discord-player/data/` | song history (the pool random mode picks from) |
| `discord-player.service` | starts the player at boot: `sudo systemctl restart discord-player` |
| `discord-player-update.timer` | nightly update at ~04:45 |

None of these are in git, and re-running the setup never overwrites them.

Useful commands (in `/opt/discord-player`): logs `docker compose logs -f`, update now
`docker compose pull && docker compose up -d`, pin a version with `IMAGE_TAG=v1.0.0` in `.env`.

## Development

```sh
python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"
.venv/bin/pytest -q && .venv/bin/ruff check . && .venv/bin/ruff format --check .
```

Every system change goes through `pisetup/system.py`, so the tests run the whole setup into a
scratch directory with a fake command runner (`tests/conftest.py`). Layout: `prepare.py`
(system, Docker, SD card, Wi-Fi), `audio.py` (sound cards and output), `player.py` (files,
`.env`, token, systemd units), `doctor.py` (health check), `files/` (what gets installed).
