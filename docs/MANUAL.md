# Chikara Server Manual

Chikara is the backend server for **Qlute**, a rhythm game. It's one Django project, and it handles:

- **Accounts and login** for the game and the website
- **Score submission**: replays are checked, re-simulated, and given pp and score
- **Leaderboards and rankings**: per-map leaderboards, global ranking, medals, levels
- **The beatmap catalog**: search, beatmap pages, difficulties, downloads
- **Beatmap submissions**: uploading `.osz` sets from the game, editing metadata, claiming osu! maps
- **The website**: profiles, rankings, beatmaps, news, settings, chat, friends, the support page
- **Online play** over websockets: chat (public channels, private rooms, DMs), multiplayer room relay, live notifications
- **Moderation**: reports, bans, staff roles, and the admin panel
- **Supporters**: paid supporter tags through Xsolla, with cosmetic perks

---

## Contents

1. [How it fits together](#1-how-it-fits-together)
2. [Repository layout](#2-repository-layout)
3. [Requirements](#3-requirements)
4. [Installing from scratch](#4-installing-from-scratch)
5. [Configuration](#5-configuration)
6. [Running in production](#6-running-in-production)
7. [Running locally for development](#7-running-locally-for-development)
8. [Day-to-day operations](#8-day-to-day-operations)
9. [Features in detail](#9-features-in-detail)
10. [HTTP API reference](#10-http-api-reference)
11. [Websocket protocol](#11-websocket-protocol)
12. [Database models](#12-database-models)
13. [Maintenance scripts](#13-maintenance-scripts)
14. [Troubleshooting](#14-troubleshooting)
15. [Rules for changing things safely](#15-rules-for-changing-things-safely)

---

## 1. How it fits together

```
             Qlute game (Godot)                 Web browser
                    │                                │
          HTTPS apiv2/* + WSS /ws/v1/*        HTTPS pages + apiv2/* + /ws/v1/chat
                    └───────────────┬────────────────┘
                                    ▼
                    nginx  (qlute.example.com, TLS, /static/)
                                    │  unix socket
                                    ▼
                daphne  ── Chikara.asgi:application ──┐
                 │   HTTP → Django views              │ websockets → Channels consumers
                 ▼                                    ▼
            MariaDB (all data)              Redis (Channels layer: chat, presence, relay)

                    nginx  (data.example.com) ── serves <storagepath>/ directly
                    (songs, backgrounds, avatars, banners, replays, card borders, notice images)
```

- **daphne** serves both normal HTTP and websockets through `Chikara/asgi.py`. A gunicorn unit is
  included in `put-into-systemd/`, but it isn't needed when daphne handles HTTP too, which is how production runs.
- **MariaDB** holds accounts, scores, beatmaps, moderation, chat rooms, and everything else.
- **Redis** is the Channels layer. Websocket consumers use it to talk to each other (chat messages, presence,
  multiplayer packets). Without it, online features only work inside a single process.
- **The storage folder** (`storagepath`, `/Storage/Chikara/` by default) holds every user file: songs, replays,
  avatars, and so on. A second nginx vhost (`DataURL`) serves it as plain files.
- **Sentry** collects errors (`sentry_sdk.init` in `settings.py`).

---

## 2. Repository layout

| Path | What's in it |
|---|---|
| `manage.py` | Django's management entry point |
| `Chikara/` | The project package: settings, URLs, ASGI/WSGI, and most of the site and game API |
| `Chikara/settings.py` | All settings, and the loader for `config/config.conf` |
| `Chikara/urls.py` | Every HTTP route |
| `Chikara/asgi.py` | ASGI app: HTTP + websocket routing |
| `Chikara/views.py` | The game API (`apiv2/...`), profiles, rankings, beatmap and score pages, medals, the home page |
| `Chikara/usersettings.py` | Settings page, avatar, banner, card border, password, and bio endpoints |
| `Chikara/catalog.py` | Beatmap catalog search (`apiv2/search`) |
| `Chikara/ppv2calc.py` | pp v3 / score calculator (replay simulation). See `Chikara/PP_SCORE_DESIGN.md` |
| `Chikara/passwords.py` | Password hashing (salted PBKDF2 over the client's SHA-256) |
| `Chikara/recommend.py` | "Try this next" difficulty recommendations |
| `Chikara/bbcode.py` | BBCode rendering for bios and news |
| `Chikara/consumers.py`, `routing.py` | Legacy `ws/game/` presence socket |
| `Chikara/recalc_ppv3.py` | One-shot pp/score recalculation for every score ([§13](#13-maintenance-scripts)) |
| `Chikara/rebuildpp.py`, `rebuildscores.py`, `oldr.py`, `new.py` | Old scripts and old copies. Don't use them ([§13](#13-maintenance-scripts)) |
| `Chikara/MEDALS.md` | How every medal is earned |
| `dbview/` | Core models: `User`, `Score`, `Beatmap`, `Beatmapset`, `Hashes`, plus the login-cookie middleware |
| `online/` | Websockets: chat, multiplayer relay, notifications. Also friends, favorites, comments. `PROTOCOL.md` is the spec |
| `moderation/` | Staff, reports, bans, notices, card borders, news, supporters, Xsolla payments, the `staff` command |
| `submissions/` | `.osz` uploads, metadata editing, osu! map claims |
| `chat/` | Old example chat socket (`ws/chat/<room>/`). The real chat is in `online/` |
| `static/` | Website HTML templates, CSS, JS, images, and Django admin assets |
| `config/` | `config.conf` (secrets, not in git) |
| `motd` | Message of the day shown in the game |
| `put-into-systemd/` | systemd units for daphne / gunicorn, plus nginx notes |
| `backups/` | Snapshots of older page designs |

---

## 3. Requirements

**System:**

- Debian or Ubuntu (production is on Debian 13)
- Python 3.10 or newer (production uses 3.13)
- MariaDB (or MySQL)
- Redis
- nginx
- A TLS certificate for the site domain and the data domain

**Python packages.** `requirements.txt` lists `sentry-sdk django channels channels-redis daphne pillow`, but
the code also imports these, so install them too:

| Package | Used for |
|---|---|
| `mysqlclient` | Django's MySQL/MariaDB driver |
| `redis` | Used directly by the online consumers |
| `requests` | Xsolla API calls |
| `ossapi` | osu! API (fetching beatmap metadata) |
| `mysql-connector-python` | Only the old standalone scripts |

```bash
pip install -r requirements.txt mysqlclient redis requests ossapi
```

> `mysqlclient` needs build headers: `sudo apt install pkg-config default-libmysqlclient-dev build-essential python3-dev`.

---

## 4. Installing from scratch

These steps set up a fresh server. Swap in your own paths, user, and domains.

### 4.1 System packages

```bash
sudo apt update
sudo apt install python3 python3-venv python3-dev build-essential pkg-config \
                 default-libmysqlclient-dev mariadb-server redis-server nginx git
sudo systemctl enable --now mariadb redis-server nginx
```

### 4.2 Get the code

```bash
sudo mkdir -p /qlute-devdj && sudo chown $USER:www-data /qlute-devdj
git clone <repo-url> /qlute-devdj
cd /qlute-devdj
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt mysqlclient redis requests ossapi
```

### 4.3 Database

```bash
sudo mariadb
```
```sql
CREATE DATABASE qluta CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'qluta'@'localhost' IDENTIFIED BY '<a strong password>';
GRANT ALL PRIVILEGES ON qluta.* TO 'qluta'@'localhost';
FLUSH PRIVILEGES;
```

Then put the same name, user, and password in `DATABASES` in `Chikara/settings.py`.

### 4.4 Storage folder

Create the storage root and the subfolders the code writes to:

```bash
sudo mkdir -p /Storage/Chikara/{songs,song_assets,song_processing,submit_tmp,replays,pfp,banners,cardborders,events}
sudo chown -R $USER:www-data /Storage/Chikara
```

| Folder | Holds |
|---|---|
| `songs/` | `.osz` beatmap set archives (downloads) |
| `song_assets/` | Extracted backgrounds, audio previews, chart files |
| `song_processing/`, `submit_tmp/` | Scratch space while uploads are processed |
| `replays/` | Submitted replays (`.qrf`) |
| `pfp/`, `banners/` | User avatars and profile banners |
| `cardborders/` | Card border images, managed from the admin panel |
| `events/` | Home-screen notice images |

### 4.5 Configuration

Start the app once, or run `python manage.py check`. That creates `config/config.conf` and writes a fresh
`secretkey=` into it. Then fill in the rest ([§5](#5-configuration)).

### 4.6 Create the tables

```bash
python manage.py migrate
```

### 4.7 Static files

nginx serves `/static/` straight from the repo's `static/` folder (`STATIC_ROOT = 'static'`), so nothing
needs collecting for the site's own files. If you change Django admin assets, run `python manage.py collectstatic`.

### 4.8 First admin

Register an account (in the game, or `POST apiv2/signup/...`), then make it an admin:

```bash
python manage.py staff add <username> --role admin
```

That account can now open `/admin` on the website and add more team members from there.

### 4.9 Services and nginx

See [§6](#6-running-in-production).

### 4.10 Allowed game builds (optional)

Score submission is refused for game builds whose hash isn't in the `Hashes` table, with "Please update to the
latest version". The game sends `User-Agent: Qlute-<hash>`. Add each release's hash to the table (with the
Django shell or SQL) when you ship it:

```bash
python manage.py shell -c "from dbview.models import Hashes; Hashes.objects.create(ostype='linux', hash='<build hash>')"
```

---

## 5. Configuration

There are two places for settings:

### 5.1 `config/config.conf` (secrets, not in git)

This is a plain `key=value` file. Lines starting with `#` are ignored, and values may contain `=`.

| Key | Meaning |
|---|---|
| `secretkey` | Django `SECRET_KEY`. Generated automatically if missing |
| `storagepath` | Storage root. Default `/Storage/Chikara/`. Keep the trailing `/` |
| `osu_client_id`, `osu_client_secret` | osu! OAuth app for beatmap claims. Create one at osu.ppy.sh → Account settings → OAuth, with callback `https://<site>/osu/callback` |
| `xsolla_project_id` | Xsolla project ID |
| `xsolla_api_key` | Xsolla API key |
| `xsolla_webhook_secret` | Xsolla webhook secret |
| `xsolla_sandbox` | `true` (test cards only) or `false` (real payments). Default `true` |

Claims and supporter checkout turn themselves off when their keys are missing.

### 5.2 `Chikara/settings.py`

| Setting | Meaning |
|---|---|
| `DEBUG` | Currently `True`. Set to `False` for a public server |
| `ALLOWED_HOSTS` | Currently `["*"]`. Narrow it to your domains in production |
| `DATABASES` | MariaDB connection |
| `CHANNEL_LAYERS` | Redis at `127.0.0.1:6379`. Set `CHIKARA_INMEMORY_CHANNELS=1` in the environment to use memory instead (one process only, for local testing) |
| `ONLINE_CHAT_CHANNELS` | Public chat channels. **Only append**; names are kept forever |
| `ONLINE_REQUIRE_GAME_HASH` | Only builds in `Hashes` may use chat and multiplayer |
| `SiteURL` | Public site address (canonical links, sitemap, social previews) |
| `DataURL` | Public address of the storage vhost. Asset, song, avatar, and banner URLs are built from it |
| `NoProfilePictureURL`, `CheaterCardBorder` | Default avatar and restricted-player border |
| `SUPPORT_URL` | Where "become a supporter" links point |
| `SUPPORTER_ITEM_SKU` | The Xsolla item that equals one month of supporter |
| `SUPPORTER_MONTH_PRICE` | Price **shown** on `/support`. Xsolla's catalog price is what's actually charged, so keep them in sync |
| `SUPPORTER_PLANS` | Month counts offered (`[1, 2, 4, 6, 12]`) |
| `TIME_ZONE` | `America/New_York`. `USE_TZ = False` |
| `sentry_sdk.init(dsn=...)` | Point it at your own Sentry project, or remove it |

Other switches are at the top of `Chikara/views.py`. For example, `allowsubmissions` turns score submission on or off.

> **Security note:** `settings.py` is in git and currently contains the database password and the Sentry DSN.
> On a public repo, move them into `config.conf` (the same loader pattern already used for the other keys)
> and change the database password.

---

## 6. Running in production

### 6.1 daphne (HTTP + websockets)

`/etc/systemd/system/daphne.service`:

```ini
[Unit]
Description=daphne (Chikara: website, API, websockets)
After=network.target redis-server.service mariadb.service
Wants=redis-server.service

[Service]
User=<you>
Group=www-data
WorkingDirectory=/qlute-devdj
RuntimeDirectory=daphne
RuntimeDirectoryMode=0755
Environment=DJANGO_SETTINGS_MODULE=Chikara.settings
ExecStart=/path/to/daphne -u /run/daphne/daphne.sock Chikara.asgi:application
Restart=always

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now daphne
```

> systemd doesn't support comments at the end of a line. Keep `# ...` comments on their own lines.
> If you used a venv, `ExecStart` must point at `.venv/bin/daphne`.

**Optional gunicorn:** `put-into-systemd/gunicorn.{service,socket}` run the WSGI app on `/run/gunicorn.sock`. Use it
only if you want plain HTTP on a separate process pool. In that case, send `/` to gunicorn and only `/ws/` to daphne.

### 6.2 nginx

```nginx
upstream qlute {
    server unix:/run/daphne/daphne.sock;
}

server {
    listen 443 ssl;
    server_name qlute.example.com;
    # ssl_certificate / ssl_certificate_key ...

    client_max_body_size 1m;   # uploads arrive in 768 KiB chunks, so 1 MB is enough

    location = /favicon.ico { access_log off; alias /qlute-devdj/static/img/favicon.ico; }
    location /static/       { root /qlute-devdj; }

    location /ws/ {
        proxy_pass         http://qlute;
        proxy_http_version 1.1;
        proxy_set_header   Upgrade $http_upgrade;
        proxy_set_header   Connection "upgrade";
        proxy_set_header   Host $host;
        proxy_read_timeout 120s;
    }

    location / {
        proxy_pass       http://qlute;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}

# The data domain: user files served straight from the storage folder.
server {
    listen 443 ssl;
    server_name data.example.com;
    location / { root /Storage/Chikara; }
}
```

```bash
sudo nginx -t && sudo systemctl reload nginx
```

### 6.3 Xsolla (if you sell supporter tags)

1. In the Xsolla Publisher Account, create a virtual item with SKU `QluteSupporter` (or whatever
   `SUPPORTER_ITEM_SKU` is). One item is one month.
2. Set the webhook URL to `https://<site>/apiv2/xsolla`.
3. Put the project ID, API key, and webhook secret in `config.conf`. Leave `xsolla_sandbox=true` until you've
   tested a purchase with a test card.
4. When you set `xsolla_sandbox=false`, orders Xsolla marks as sandbox are ignored, so test purchases never
   grant real supporter time.

### 6.4 Applying changes

| You changed | Do this |
|---|---|
| Any `.py` file | `sudo systemctl restart daphne` |
| A model | `python manage.py makemigrations <app> && python manage.py migrate`, then restart daphne |
| HTML/CSS/JS in `static/` | Nothing to restart. Bump the `?v=` query on the asset link so browsers fetch the new file |
| `config.conf` | Restart daphne |
| `motd` | Nothing. It's read on every request |
| nginx config | `sudo nginx -t && sudo systemctl reload nginx` |

---

## 7. Running locally for development

```bash
source .venv/bin/activate
export CHIKARA_INMEMORY_CHANNELS=1      # no Redis needed
python manage.py migrate
python manage.py runserver 0.0.0.0:8000 # daphne is in INSTALLED_APPS, so runserver serves websockets too
```

You still need a MariaDB database, or you can point `DATABASES` at a local copy. Use `xsolla_sandbox=true`.
To make the game connect to your local server, change the server address in the Qlute client.

---

## 8. Day-to-day operations

### Logs

```bash
journalctl -u daphne -f          # app logs and tracebacks
journalctl -u nginx              # or /var/log/nginx/*.log
```

Errors also go to Sentry.

### Team / staff

- From the shell: `python manage.py staff list | add NAME [--role admin|mod] | remove NAME`
- From the website: `/admin` → Staff. Admins only.

**Roles:**

| | Mod | Admin |
|---|---|---|
| Handle reports | ✓ | ✓ |
| Ban and unban players | ✓ (not other staff) | ✓ (not other admins) |
| Accept or decline beatmap claims | ✓ | ✓ |
| Write news | ✓ | ✓ |
| Add or remove staff | | ✓ |
| Edit notices and card borders | | ✓ |
| Grant supporter time | | ✓ |

Every team member gets the team medal and supporter perks.

### Bans

- Issued from `/admin` with a reason and an optional length (up to 10 years).
- A ban sets `users.restricted`. Restricted players can't submit scores, chat, or interact. Their profile shows the
  restricted notice and the cheater border.
- Timed bans expire *lazily*. They're cleared when the player next logs in or when a team member opens the admin panel.
- Accounts you restrict by hand in the database (with no `Ban` row) are never lifted automatically.

### Message of the day

Edit the `motd` file in the repo root. The game shows it on the menu.

### Home-screen notices

`/admin` → Notices (admins). Images go in `<storage>/events/`. Each notice has text, a click-through link,
a position, and an on/off switch.

### News

`/admin` → News. Posts support BBCode, a cover image, drafts, and pinning. They show at `/news`.

### Backups

What to back up:

1. **The database:** `mariadb-dump qluta | gzip > qluta-$(date +%F).sql.gz`
2. **The storage folder** (`/Storage/Chikara`): replays and uploaded maps can't be rebuilt from anything else.
3. **`config/config.conf`**: it holds the secret key and API keys.

---

## 9. Features in detail

### 9.1 Accounts and login

- The game hashes the password with **SHA-256** and sends the hex string. The server stores a **salted PBKDF2** of
  that (`Chikara/passwords.py`). Accounts still on the old unsalted SHA-256 are flagged with
  `change_password: true` at login, and the website sends them to `/changepassword`.
- **The game** authenticates every request with `Username` and `Password` headers.
- **The website** stores `username` and `password` (the SHA-256) cookies after `POST apiv2/login`. Requests that
  change data from the website must also send the header `X-Chikara: 1`. A cross-site form can't send that header,
  which is how the site guards against CSRF.
- `dbview.dailycheck.CheckUserAuthMiddleware` clears the login cookies when they stop being valid.

### 9.2 Scores, pp, and ranking

- The game posts a replay to `apiv2/ss`. The server checks login, restriction, the Auto mod, and the game hash.
  Then it saves the replay to `<storage>/replays/` and **re-simulates it** with `ppv2calc` to get judgements, combo,
  pp, and score. The client's numbers aren't trusted.
- **Score:** 0 to 1,000,000 on NoMod (90% accuracy, 10% combo), multiplied by the mod multiplier.
  **pp:** comes from a strain-based star rating. The full formulas are in `Chikara/PP_SCORE_DESIGN.md`. The game has
  a bit-identical copy of the calculator, so **change both together**.
- Each player keeps one row per map: their best by score.
- A player's total pp is the 0.95ⁿ-weighted sum of their best 100 plays. The global ranking (`/ranking`) is sorted by it.
- Beatmap status (`ranked`): `1` ranked, `2` special, `0` unranked. Only ranked plays count toward rankings.

### 9.3 Medals

Medals are computed live from stats and never stored. There are 34. The rules are in `Chikara/MEDALS.md`.
New medals must be **appended** to the list, because the game identifies medals by position.

### 9.4 Beatmaps

- **The catalog** (`Chikara/catalog.py`, `apiv2/search`) powers the website's `/beatmaps`, the game's Browse screen,
  and multiplayer lookups. It filters by status, genre, language, explicit content, and more
  (`apiv2/beatmapfilters` lists the options).
- Metadata for maps crawled from osu! is fetched with `ossapi`.
- **Beatmap pages:** `/beatmapset/<id>`, with a leaderboard per difficulty, favorites, and comments.
- **Score pages:** `/score/<id>`. Replays download from `apiv2/getreplay/<id>`.

### 9.5 Submissions (`submissions/`)

- The game uploads `.osz` files in 768 KiB chunks (`start` → `chunk` → `finish`), because nginx limits request
  bodies to 1 MB. `osz.py` unpacks the archive, reads the `.osu` files, extracts assets, and creates the set.
- Uploading a set again with the same `BeatmapSetID` updates it, as long as it's still unranked.
- Owners and the team can edit metadata on the website. Only the team can change ranked status.
- **osu! claims:** a player logs in with osu! (`/osu/claim/<setid>` → `/osu/callback`). If their osu! account made
  that set, a claim is created. The team then accepts or declines it in `/admin`. An accepted claim makes the player
  the set's owner.

### 9.6 Social

- **Friends:** one-way, and called mutual when both sides add each other. They're on `/friends` and in the game.
- **Favorites and comments** on beatmap sets.
- **Notifications:** stored in `online.Notification` and pushed live over `/ws/v1/notify/`.
- **Chat:** public channels (`#general`, `#multiplayer`, `#help`), private rooms with invites, and DMs.
  It's available in the game and at `/chat` on the website.

### 9.7 Multiplayer

The server **doesn't run game logic**. The host's game runs the room the same way it would on a LAN, and the
server lists rooms and forwards packets between players (`online/relay_consumer.py`). It also supports host
migration when the host leaves. See [§11](#11-websocket-protocol).

### 9.8 Moderation

Players report from the game or the website (`POST apiv2/mod/report`), with a limit of 10 per hour. The team works
through reports, bans, users, staff, claims, news, notices, card borders, and supporters in the `/admin` panel,
which is backed by `apiv2/mod/...`.

### 9.9 Supporters

Players buy 1, 2, 4, 6, or 12 months on `/support`, for themselves or as a gift. Payment goes through Xsolla Pay
Station in a popup. The order is confirmed by the webhook, and also by polling Xsolla directly, so it still
completes if the webhook is late. Admins can also grant time by hand.

**Perks** are cosmetic only and never affect gameplay or ranking:

- Profile banner
- Supporter name style and heart in chat and on profiles
- Supporter-only card borders
- Higher limits:

| | Everyone | Supporters |
|---|---|---|
| Friends | 500 | 1,000 |
| Private rooms | 20 | 50 |
| Favorites | 2,000 | 5,000 |
| Bio length | 3,000 | 6,000 |

---

## 10. HTTP API reference

All routes are in `Chikara/urls.py`. The game authenticates with `Username` and `Password` (SHA-256) headers.
The website uses its cookies, plus `X-Chikara: 1` on writes.

### Game / core (`Chikara/views.py` → `api`)

| Method | Path | What it does |
|---|---|---|
| POST | `apiv2/signup/...` | Create an account (headers `Username`, `Password`) |
| POST | `apiv2/login` | Website login (form `username`, `password`). Sets cookies |
| POST | `apiv2/ss` | Submit a score (replay in the body; headers `Username`, `Password`, `Mods`, ...) |
| GET | `apiv2/getuser/<name>` | Public profile JSON |
| GET | `apiv2/getstat/<what>` | One stat for the logged-in player (`score`, `level`, `rank`, `pfp_path`, `full`, ...) |
| GET | `apiv2/listmedal/<name>` | Medals: `[{title, desc, achieved}]` |
| GET | `apiv2/getonline` | Online players |
| GET | `apiv2/getdifficulties` | Difficulties of a set (header `BeatmapSetID`) |
| GET | `apiv2/getleaderboard` | Map leaderboard (header `BeatmapID`) |
| GET | `apiv2/getreplay/<scoreid>` | Download a replay (`.qrf`) |
| GET | `apiv2/s/<beatmapid>` | A map's ranked status |
| GET | `apiv2/rankstatus` | Ranked status lookup |
| GET | `apiv2/search` | Beatmap catalog search |
| GET | `apiv2/beatmapfilters` | Catalog filter options |
| GET | `apiv2/recommendation` | Recommended difficulties |
| GET | `apiv2/searchusers`, `searchplayers`, `searchscores` | Search |
| GET | `apiv2/getnotice`, `menunotice` | Home-screen notices and MOTD |
| GET | `apiv2/cardborders`, `pfps` | Available borders and avatars |
| GET | `apiv2/setstatus` | Update the player's status text |
| GET | `apiv2/chkprofile` | Check login / profile state |

### User settings (`Chikara/usersettings.py`)

`apiv2/avatar`, `apiv2/banner`, `apiv2/cardborder`, `apiv2/password`, `apiv2/bio[/<action>]`

### Social (`online/`)

| Path | What it does |
|---|---|
| `apiv2/friends`, `apiv2/friends/add/<name>`, `apiv2/friends/remove/<name>` | Friends |
| `apiv2/favorites[/<action>]` | Favorite beatmap sets |
| `apiv2/comments/<action>` | Beatmap comments |
| `apiv2/notifications[/<action>]` | List notifications and mark them read |

### Submissions (`submissions/views.py`)

| Method | Path | What it does |
|---|---|---|
| POST | `apiv2/submit/start` | `{size, name}` → `{token, chunk_size}` |
| POST | `apiv2/submit/chunk/<token>?offset=N` | Raw bytes |
| POST | `apiv2/submit/finish/<token>` | Process the upload → set id, difficulties |
| GET | `apiv2/submit/info/<setid>` | Editable fields |
| POST | `apiv2/submit/edit/<setid>` | Edit metadata |
| GET | `apiv2/submit/mine` | Your sets |
| GET | `apiv2/submit/claim/<setid>` | Claim status |

### Moderation (`moderation/views.py`)

| Who | Path | What it does |
|---|---|---|
| Anyone logged in | `GET apiv2/mod/me`, `POST apiv2/mod/report` | Your role; file a report |
| Team | `apiv2/mod/reports`, `report`, `users`, `user`, `ban`, `unban`, `bans`, `staff`, `notices`, `supporters`, `borders`, `claims`, `news` | The admin panel. GET reads, POST changes |

### Supporters (`moderation/payments.py`)

| Path | What it does |
|---|---|
| `POST apiv2/support/checkout` | `{plan, gift}` → Pay Station URL |
| `GET apiv2/support/order/<id>` | Order status |
| `POST apiv2/xsolla` | Xsolla webhook. Signed; don't call it yourself |

### Website pages

| Path | Page |
|---|---|
| `/` | Home |
| `/user/<name>` | Profile |
| `/ranking` | Rankings |
| `/beatmaps`, `/beatmapset/<id>` | Beatmaps |
| `/score/<id>` | Score |
| `/search` | Search |
| `/friends` | Friends |
| `/chat` | Chat |
| `/settings`, `/changepassword` | Account settings |
| `/support` | Supporter page |
| `/news`, `/news/<id>` | News |
| `/admin` | Admin panel |
| `/osu/claim/<setid>` | Start an osu! claim |
| `/sitemap.xml`, `/robots.txt` | For search engines |

---

## 11. Websocket protocol

The full spec is in **`online/PROTOCOL.md`**. In short:

| Path | Purpose |
|---|---|
| `/ws/v1/chat/` | Chat: channels, private rooms, DMs, presence, friend events, ban notices |
| `/ws/v1/multiplayer/` | Room list and packet relay (binary frames with a 6-byte header) |
| `/ws/v1/notify/` | Live notifications |
| `ws/game/` | Legacy presence socket |

- Auth uses the same `Username` and `Password` headers as the HTTP API. The website's `/chat` page uses cookies,
  and only from the site's own origin.
- Clients ping every ~20 seconds.
- Close code `4001` means a bad login; don't retry. `4002` means reconnect now.
- Multiplayer limits are 512 KiB per frame, 4 MiB/s, and 400 frames/s per connection.
- **Only add to v1.** Old game builds stay in use. A breaking change goes in a new `/ws/v2/...` path next to v1.

---

## 12. Database models

| App | Model | Table purpose |
|---|---|---|
| dbview | `User` | Accounts, totals, rank, avatar, banner, bio, restricted flag |
| dbview | `Score` | One row per player per map (best). Counts, pp, score, mods, replay path |
| dbview | `Beatmap` | One difficulty: metadata, pp, note count, file paths |
| dbview | `Beatmapset` | Set metadata and osu! status / Qlute ranked status |
| dbview | `Hashes` | Allowed game build hashes |
| moderation | `StaffMember` | Team roles (admin / mod) |
| moderation | `Report`, `Ban` | Reports and bans |
| moderation | `Notice`, `CardBorder`, `NewsPost` | Site content |
| moderation | `Supporter`, `SupportOrder` | Supporter time and Xsolla orders |
| submissions | `Submission`, `UploadSession`, `BeatmapClaim` | Uploaded sets, in-progress uploads, osu! claims |
| online | `PrivateChatRoom`, `PrivateChatMember`, `PrivateChatInvite`, `DirectChat` | Chat rooms and DMs |
| online | `OnlineSession`, `MultiplayerRoom` | Live presence and listed rooms |
| online | `Friend`, `FavoriteBeatmap`, `BeatmapComment`, `Notification` | Social |

Change models only through Django migrations (`makemigrations` / `migrate`).

---

## 13. Maintenance scripts

| Script | Status | Use |
|---|---|---|
| `python -m Chikara.recalc_ppv3 --dry-run` | **Current** | Recompute every beatmap's pp, re-simulate every score from its replay, rebuild every player's totals and ranking. Prints a summary and writes nothing |
| `python -m Chikara.recalc_ppv3 [--jobs 8]` | **Current** | The same, but writes the results. Run it after changing `ppv2calc.py`. Back up the database first |
| `Chikara/rebuildpp.py`, `rebuildscores.py`, `oldr.py` | Obsolete | Old pp formula. `rebuildpp.py` exits immediately. Don't run them |
| `Chikara/new.py` | Old copy | Not imported anywhere. The live code is `views.py` |
| `python manage.py staff ...` | Current | Team management ([§8](#8-day-to-day-operations)) |

Run them from the repo root with the venv active.

---

## 14. Troubleshooting

| Symptom | Likely cause / fix |
|---|---|
| 502 Bad Gateway | daphne isn't running, or the socket path doesn't match nginx. Check `systemctl status daphne` and `ls /run/daphne/` |
| Code changes don't show | Restart daphne. For static files, bump `?v=` or hard-refresh |
| Chat or multiplayer drops every few seconds | Redis is down, or `socket_timeout` was lowered. It must stay above 5 s; it's set to 30 |
| "Too many connections" from Redis | Raise `max_connections` in `CHANNEL_LAYERS` (now 2000) |
| Websocket won't connect through nginx | Check the `/ws/` block has the `Upgrade` / `Connection` headers and `proxy_http_version 1.1` |
| "Please update to the latest version" on submit | The build's hash isn't in `Hashes` ([§4.10](#410-allowed-game-builds-optional)) |
| "Submissions are disabled." | `allowsubmissions = 0` in `views.py` |
| Avatars, songs, or backgrounds 404 | `DataURL` vhost root doesn't match `storagepath`, or the file permissions are wrong |
| Upload fails partway | nginx `client_max_body_size` is below 1 MB, or `<storage>/submit_tmp` isn't writable |
| Supporter purchase never completes | Wrong webhook URL or secret, or sandbox mode doesn't match the order type. Check `SupportOrder` rows in `/admin` → Supporters |
| osu! claim button is missing | `osu_client_id` / `osu_client_secret` aren't set, or the callback URL is wrong |
| Logged out on every page | The stored password changed. The middleware clears stale cookies, so log in again |
| `django.db.utils.OperationalError` at startup | MariaDB is down or the credentials are wrong. Also check `mysqlclient` is installed |

---

## 15. Rules for changing things safely

- **Websocket protocol:** only add new ops and fields. Never rename or remove them.
- **Medals:** append only. Never insert or reorder.
- **Chat channels:** append only to `ONLINE_CHAT_CHANNELS`.
- **pp and score formulas:** change `Chikara/ppv2calc.py` **and** the game's `PerformanceCalculator.cs`
  together, then run `recalc_ppv3`.
- **Models:** always go through migrations, and back up first.
- **Static assets:** bump `?v=` when you change a CSS or JS file.
- **Secrets:** keep them in `config/config.conf`, never in git.
