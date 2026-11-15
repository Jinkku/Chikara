# Online chat + multiplayer protocol (v1)

Used by the Qlute game (`Script/Online/*.cs`). Old game versions stay in the wild, so **only add to this**:
new ops / new optional fields. Never rename or remove an op or field, or change what one means. Ignore unknown ops and
fields. If something truly has to break, add `/ws/v2/...` next to `/ws/v1/...` and keep v1 running.

## Connecting

`wss://<server>/ws/v1/chat/` and `wss://<server>/ws/v1/multiplayer/`, with the same headers as the HTTP API:

| header | value |
|---|---|
| `Username` | account name |
| `Password` | SHA-256 hex of the password (what the game stores) |
| `User-Agent` | `Qlute-<game hash>` (only checked when `ONLINE_REQUIRE_GAME_HASH = True`) |
| `Features` | optional, comma-separated: what the client understands (`ban`, `dm`, `friends`, chat only). Old clients send nothing and get the old behaviour. |

The website's chat page (`/chat`) connects to the same chat socket without those headers: a browser socket opened
from one of the site's own pages (its `Origin` matches the site) is logged in with the site's `username` / `password`
cookies and gets the `ban`, `dm` and `friends` features. Cookies from any other origin are ignored.

A bad login gets `{"op":"error","fatal":true,"text":...}` and close code 4001. Clients should not retry automatically after that.
All control messages are JSON text frames with an `"op"` field. Clients send `{"op":"ping"}` every ~20 s and get `{"op":"pong"}`.

## Chat (`/ws/v1/chat/`)

Channel ids: public channels are `#name` (from `settings.ONLINE_CHAT_CHANNELS`, everyone is in all of them),
private rooms are `p<number>`.

Client → server

| op | fields | |
|---|---|---|
| `msg` | `channel`, `text` (≤ 500) | |
| `create` | `title` (≤ 40) | new private room, you're its only member |
| `invite` | `room`, `user` | any member can invite by username |
| `accept` / `decline` | `room` | answer an invite |
| `leave` | `room` | the room is deleted when its last member leaves; for a DM (`d…`) it just hides it from your list |
| `dm_open` | `user` | (`dm`) start / reopen a DM with that player → `room` with `focus: true` |
| `online` | | ask for the online list again |

Server → client

| op | fields |
|---|---|
| `welcome` | `v`, `user`, `channels: [{id,title}]`, `rooms: [{id,title,owner,members}]`, `invites: [{room,title,from}]`, `online: [names]` |
| `history` | `channel`, `lines: [{author,text,ts,supporter}]` (last 50, oldest first) |
| `msg` | `channel`, `author`, `text`, `ts` (unix ms), `supporter` (bool: the author is a Qlute supporter, show their name specially); your own messages come back too |
| `notice` | `channel`, `text` (joined / left / invited lines) |
| `room` | `room: {id,title,owner,members}` (you joined it, or its members changed); DMs add `dm: true, with: <other player>`, and `focus: true` when you just opened it |
| `left` | `room` |
| `invite` / `invite_gone` | `room`, `title`, `from` / `room` |
| `presence` | `user`, `online` (bool) |
| `online_list` | `online: [names]` |
| `error` | `text`, `fatal` (optional) |
| `restricted` | `text`, `expires` (unix ms or null) (`ban`) your account is restricted: show it. Right after a ban the socket then closes with code `4002`; reconnect and you'll get this again, then only `unrestricted` |
| `unrestricted` | `text` (`ban`) the restriction is over; the socket closes with `4002`: reconnect for the normal welcome |
| `friend` | `user`, `added`, `mutual` (`friends`) someone added you as a friend |

### Direct messages (`dm`)

A DM's channel id is `d<lower user id>-<higher user id>`. Clients with `dm` get their recent DMs in `welcome.rooms`
(with `dm: true`), send to them with `msg`, and get them with `msg` like any room. The first message of a
conversation you don't have open arrives as `room` + `history` instead. You can't DM restricted players.

### Restricted accounts (`ban`)

Without `ban` a restricted account is refused (`error` fatal, close `4001`) and a ban drops it the same way.
With `ban` it is accepted in a listen-only mode: it gets `restricted` and nothing else (no welcome, no presence,
every other op is ignored except `ping`) until the ban is lifted or runs out, when it gets `unrestricted`.
Close code `4002` means "connect again now".

### Friends (HTTP)

`GET apiv2/friends` → `{friends: [{username, online, status, last_seen, rank, points, pfp, mutual}], followers}`,
`POST apiv2/friends/add/NAME` → `{ok, mutual}`, `POST apiv2/friends/remove/NAME` → `{ok}`. Same auth as the rest of
the API (game headers, or website cookies + `X-Chikara: 1`). Friends are one-way; both ways = `mutual`.

Limit: 8 actions per 5 seconds per connection.

## Multiplayer relay (`/ws/v1/multiplayer/`)

The room runs inside the host's game, exactly like a LAN room. The server lists rooms and forwards packets.
The host is peer `1`; players get `2, 3, ...` in join order. Players can only send to the host.

Client → server (text)

| op | fields | |
|---|---|---|
| `list` | | → `rooms` |
| `host` | `name`, `proto` (game's LAN protocol), `ver`, optional `migrate: true` | → `hosted`. `migrate`: this game can take a room over (see below) |
| `update` | any of `name`, `players`, `phase`, `map`, `next` | host only; also keeps the room listed (send every ≤ 15 s). `next`: peer id that should take over if the host leaves |
| `join` | `room` | → `joined` or `join_failed` |
| `kick` | `peer` | host only |
| `leave` | | leave / close your room but keep the socket |

Server → client (text)

| op | fields |
|---|---|
| `rooms` | `rooms: [{id,name,host,players,phase,map,proto,ver}]` |
| `hosted` | `room`, `peer` (=1) |
| `joined` | `room`, `peer` |
| `join_failed` | `text` |
| `peer_connected` | `peer`, `user` (host only; `user` is the verified account name) |
| `peer_disconnected` | `peer` (host only) |
| `closed` | `reason` (players: the host left or removed you) |
| `promoted` | `room`, `old_peer`, `peers: [{peer,user}]` (you're peer `1` now and run the room; `old_peer` was your id) |
| `host_moved` | `room`, `old_peer` (the host left; peer `1` is now the player who had id `old_peer`) |

### Host migration

When a host that sent `migrate: true` leaves (or its connection drops) while players are in the room, the room is not
closed. The server picks the host's last `next` if that peer is still there, otherwise the lowest peer id. That player
gets `promoted` and becomes peer `1`; everyone else gets `host_moved` and keeps their own peer id. Players should
reset their connection state and say hello to the new host again. The room keeps its id; its listing's `host` becomes
the new host's account name. Hosts that didn't send `migrate` close the room for everyone, as before.

Binary frames carry game packets: a 6-byte header `int32 LE peer, uint8 channel, uint8 transfer mode`, then the payload.
Sending, `peer` is the target (`0` = all players, `-N` = all but N, ignored for players). Receiving, it's the sender.
Limits: 512 KiB per frame, 4 MiB/s and 400 frames/s per connection (frames over the limit are dropped).
