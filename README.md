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
| `--youtube-cookies cookies.txt` | sign in to YouTube with a spare account (see below) |
| `--token-stdin` | read the token from stdin: `echo "$TOKEN" \| sudo python3 -m pisetup --token-stdin` |
| `--no-upgrade` | skip the slow apt upgrade (quick re-run) |
| `--no-start` | install, but don't start the player |

Run it again any time, e.g. after a `git pull` or to switch the output to a USB sound card:
`sudo python3 -m pisetup --no-upgrade --audio usb`. Your settings, token and song history are
kept; only the options you pass change.

### If YouTube asks to confirm the Pi isn't a bot

After many downloads YouTube may flag your internet address, and the player says in Discord
that YouTube wants it to prove it isn't a bot. It then waits 30 minutes and tries again by
itself; on a home connection the block usually clears within hours or a few days.

If it keeps coming back, let the player sign in with the cookies of a **spare** Google account.
YouTube can ban accounts used this way, so never use your own.

1. On your computer, open a **private/incognito** browser window, sign in to youtube.com with
   the spare account and play any video.
2. In that window, export the cookies with a cookies.txt extension (e.g. *Get cookies.txt
   LOCALLY*) as `cookies.txt`, then close the window without signing out (signing out makes
   the cookies useless).
3. Copy it to the Pi and install it (the player restarts and signs in with it):
   ```sh
   scp cookies.txt <username>@musicpi.local:~
   cd ~/rasbery-setup-player && sudo python3 -m pisetup --no-upgrade --youtube-cookies ~/cookies.txt
   rm ~/cookies.txt
   ```

The cookies are stored like the bot token, in `/opt/discord-player/secrets/youtube_cookies`
(readable only by the player). They stop working after some weeks or months; repeat the steps
then. To sign out again, empty that file and restart the player.

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
| `/opt/discord-player/secrets/youtube_cookies` | optional YouTube sign-in (empty = not signed in), also a Docker secret |
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
