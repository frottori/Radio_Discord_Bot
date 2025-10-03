# Radio_Discord_Bot

A Discord bot that streams a radio station into a voice channel, tracks recently played songs, and (optionally) fetches song metadata from Spotify.

Quick pointers:
- Main implementation: [radio.py](radio.py)
- Example environment variables: [.env.example](.env.example)
- Dependencies: [requirements.txt](requirements.txt)
- License: [LICENSE](LICENSE)

## Features
- Join a user's voice channel and stream a radio URL into the channel (/radio) — implementation: [`radio`](radio.py).
- Pause/resume the audio stream (/pause, /resume) — implementations: [`pause`](radio.py), [`resume`](radio.py).
- Stop and disconnect the bot (/stop) — implementation: [`stop`](radio.py).
- Show current song from a station API (/nowplaying) using [`get_title_from_api`](radio.py) and detect commercial breaks with [`get_title_normalized`](radio.py).
- Fetch richer metadata (artists, album, cover, Spotify link) via Spotify using [`get_song_details`](radio.py) and display it with [`populate_np_embed`](radio.py).
- Maintain a rolling history of up to 50 last played songs and display them with [`lastplayed`](radio.py) and [`populate_lp_embed`](radio.py).
- Background updater that polls the station API and updates history/status: [`update_song_history`](radio.py).
- Bot activity status updated via [`update_activity`](radio.py).

## Requirements
- Python 3.10+ recommended.
- FFmpeg installed on the host for voice streaming (used by discord.py FFmpeg audio source).
- A Discord bot token and a server where you can add the bot.
- (Optional) Spotify developer credentials if you want detailed song metadata.

Install Python dependencies:
```sh
pip install -r requirements.txt
```
See: [requirements.txt](requirements.txt)

## Configuration
1. Copy `.env.example` to `.env`:
   - See the template at [.env.example](.env.example)
2. Fill required variables:
   - DISCORD_TOKEN — your Discord bot token (required)
   - RADIO_URL — streaming URL for the radio (required)
   - SONGS_URL — JSON API endpoint that returns current track info (recommended)
   - KEYWORD — a keyword used to detect commercial breaks in the returned title (recommended)
   - SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET — optional, for Spotify metadata

> Important: Keep the `.env` secret. The repo already lists `.env` in [.gitignore](.gitignore).

## Bot Setup (Discord)
1. Create a bot in the Discord Developer Portal and copy the token into `DISCORD_TOKEN`.
3. Invite the bot to your server with scopes `bot` and `applications.commands`, and grant it the permissions to connect and speak in voice channels

## How to run
Start the bot from the project root:
```sh
python radio.py
```
The bot will:
- Load env variables via python-dotenv.
- Connect to Discord using `DISCORD_TOKEN`.
- Sync slash commands on ready.
- Start the background poller [`update_song_history`](radio.py) which runs every minute (configurable in code).

## Slash commands
- /radio — join your voice channel and stream the configured `RADIO_URL` ([`radio`](radio.py)).
- /pause — pause playback ([`pause`](radio.py)).
- /resume — resume playback ([`resume`](radio.py)).
- /stop — stop and disconnect ([`stop`](radio.py)).
- /nowplaying — show the currently playing song (uses [`get_title_from_api`](radio.py) and [`get_song_details`](radio.py)).
- /lastplayed — show recent songs saved in memory ([`lastplayed`](radio.py)`).

## API expectations
The `get_title_from_api` helper expects `SONGS_URL` to return JSON with an "icestats" object that includes a "title" field somewhere inside a nested dict. Adjust logic in [`get_title_from_api`](radio.py) if your station's API format differs.

## Troubleshooting & Tips
- If slash commands don't appear immediately, wait up to an hour for global sync or use a guild-specific sync during development by modifying `bot.tree.sync()` in [radio.py](radio.py).
- If Spotify metadata is not shown, ensure `SPOTIFY_CLIENT_ID` and `SPOTIFY_CLIENT_SECRET` are set and valid.
- If streaming fails, verify FFmpeg is available on PATH and `RADIO_URL` is a valid stream.
- The bot prints warnings when optional config is missing; check console logs for messages printed by [radio.py](radio.py).

## Security and privacy
- Do not commit your `DISCORD_TOKEN` or Spotify credentials. Use `.env` or a secrets manager.
- The bot keeps an in-memory history (`song_history`) of last songs (up to 50) and does not persist them to disk.

## License
This project is covered under the terms in [LICENSE](LICENSE).