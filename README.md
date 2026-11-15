# Chikara

Chikara is the server behind **Qlute**, a rhythm game. It runs the game's online services and its website:

- **Accounts and login** for the game and the website
- **Score submission.** Replays are re-simulated on the server to work out pp and score, so the client's numbers aren't trusted
- **Leaderboards, global rankings, levels and medals**
- **A beatmap catalog** with search, beatmap pages, downloads, favorites and comments
- **Beatmap uploads** from the game, metadata editing, and claiming maps made on osu!
- **Online play over websockets:** chat channels, private rooms, DMs, friends, live notifications and a multiplayer room relay
- **Moderation:** reports, bans, staff roles and an admin panel
- **Supporter tags** sold through Xsolla, with cosmetic perks only

It is built with Django and Channels, served by daphne behind nginx, and uses MariaDB for data and Redis for the websocket layer.

> [!NOTE]
> Qlute builds from 2024.11.10 or earlier are no longer supported and can't connect to the server.

## Documentation

| Document | Covers |
|---|---|
| [docs/MANUAL.md](docs/MANUAL.md) | The full manual: setup, configuration, production, operations, features, API reference, troubleshooting |
| [online/PROTOCOL.md](online/PROTOCOL.md) | The websocket protocol for chat and multiplayer |
| [Chikara/PP_SCORE_DESIGN.md](Chikara/PP_SCORE_DESIGN.md) | How pp and score are calculated |
| [Chikara/MEDALS.md](Chikara/MEDALS.md) | Every medal and how to earn it |
| [put-into-systemd/](put-into-systemd/) | systemd units and nginx notes |

## Requirements

- Debian or Ubuntu
- Python 3.10 or newer
- MariaDB (or MySQL)
- Redis
- nginx

## Quick start

These commands give you a working server. The [manual](docs/MANUAL.md#4-installing-from-scratch) explains each step and covers production details: TLS, systemd, the storage domain and Xsolla.

```bash
# 1. System packages
sudo apt install python3 python3-venv python3-dev build-essential pkg-config \
                 default-libmysqlclient-dev mariadb-server redis-server nginx git

# 2. Code and Python packages
git clone https://github.com/Jinkku/Chikara && cd Chikara
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt mysqlclient redis requests ossapi

# 3. Database: create the database and user in MariaDB, then set DATABASES in Chikara/settings.py
sudo mariadb -e "CREATE DATABASE qluta CHARACTER SET utf8mb4;
                 CREATE USER 'qluta'@'localhost' IDENTIFIED BY 'change-me';
                 GRANT ALL PRIVILEGES ON qluta.* TO 'qluta'@'localhost';"

# 4. Storage folder for songs, replays, avatars and other user files
sudo mkdir -p /Storage/Chikara/{songs,song_assets,song_processing,submit_tmp,replays,pfp,banners,cardborders,events}
sudo chown -R $USER:www-data /Storage/Chikara

# 5. Tables, then the first admin (register the account first)
python manage.py migrate
python manage.py staff add <username> --role admin

# 6. Run it
python manage.py runserver 0.0.0.0:8000
```

To try it locally without Redis, set `CHIKARA_INMEMORY_CHANNELS=1` before starting the server. This only works with a single process.

## Configuration

Secrets go in `config/config.conf`. It isn't tracked by git and is created on first start with a generated `secretkey`.

```ini
storagepath=/Storage/Chikara/
osu_client_id=            # osu! OAuth app, for beatmap claims
osu_client_secret=
xsolla_project_id=        # supporter purchases
xsolla_api_key=
xsolla_webhook_secret=
xsolla_sandbox=true
```

Everything else, such as site URLs, chat channels and supporter plans, is in `Chikara/settings.py`. See [Configuration](docs/MANUAL.md#5-configuration) in the manual.

## Production

In production, daphne serves the whole app (HTTP and websockets) on a unix socket, and nginx proxies to it. A second nginx site serves the storage folder as the data domain. After changing Python code, restart daphne:

```bash
sudo systemctl restart daphne
```

See [Running in production](docs/MANUAL.md#6-running-in-production) for the unit file and nginx config.

## Project layout

| Path | Contents |
|---|---|
| `Chikara/` | Settings, URLs, the game API, website pages, and the pp calculator |
| `dbview/` | Core models: users, scores, beatmaps |
| `online/` | Chat, multiplayer relay, notifications, friends, favorites, comments |
| `moderation/` | Staff, reports, bans, news, notices, card borders, supporters, payments |
| `submissions/` | Beatmap uploads and osu! claims |
| `static/` | Website templates, CSS, JS and images |
| `config/` | `config.conf` (local only) |

## Contributing

- The websocket protocol, the medal list and the chat channel list are append-only, because older game builds depend on them.
- pp and score formulas also live in the game client. Change both together, then run `python -m Chikara.recalc_ppv3`.
- Change models through Django migrations, and keep secrets out of git.

## License

Chikara is licensed under the [MIT License](LICENSE). You can do what you like with it, as long as you keep the copyright and license notice.
