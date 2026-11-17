# Medals

Medals are worked out live from a player's stats every time someone asks, so a player gets a medal the moment they
qualify. The first time a medal shows up as earned it's recorded (`online.MedalUnlock`, below), and from then on it
**stays earned forever**, even if the play or stat behind it changes later (a better score replaces the qualifying
play, levels get recalculated...). The exceptions are the medals about where a player is right now, `LIVE_MEDALS`:
The End, Top 1,000 / 100 / 50 / 10, Supporter, Making the game better and Team Moderator. Those come and go.

- **Code:** `Chikara/views.py`: `medals` (the original 16), `EXTRA_MEDALS` (the 18 added later),
  `getmedals()`, `_extra_medal_checks()` and `_medal_clears()`.
- **Where they show up:** the profile page (`views.user()`, "Medals · N / 47 earned"), the classic profile, the public
  profile JSON (`public_profile()`, `"medals"`), and the game's `listmedal/<username>` API
  (`[{"title", "desc", "achieved"}]`).
- **Hover hints:** on the profile, hovering a medal (or tapping it on a phone) shows how to earn it, prefixed with
  "Got it!" once earned. The text is `MEDAL_HINTS` for the original medals and the "how to earn" field of
  `EXTRA_MEDALS`. Styles are in `static/css/profile.css` (`.pf-medal::after`).
- **Order matters.** Both the original medals and the game client go by position in the list, so new medals are
  always **appended** to the end. Never insert or reorder.

## Unlocks and the "Medal unlocked!" popup

Whether a medal is earned is still worked out live, but the **first time** each one shows up as earned is recorded in
`online.MedalUnlock` (`online/medals.py`). That's what drives the popups:

- **Game:** a "Medal unlocked!" card per new medal, under the top bar (`Qlute/Script/Medals/MedalPopup.cs`). Several
  at once stack (3 on screen, the rest behind a "+N more" pill); none show during gameplay. The game gets new medals
  from the score-submit reply (`apiv2/ss` → `"medals"`) and from `GET apiv2/medals/new`, which it asks right after
  login and every 3 minutes. Each unlock is handed to the game once (`MedalUnlock.seen`).
- **Website:** a `medal` notification (bell + toast, gold styling in `static/css/headerbuttons.css`) linking to
  `/user/<name>#medals`.
- **Profiles:** hovering an earned medal says when it was earned ("Got it on 15 Nov 2026!"); `public_profile()`
  sends `achieved_at` (unix, 0 = unknown).
- **Checked:** after every score submission, on the game's polls, and right after the website actions that can earn
  one (a mutual friend, a favourite, a comment, a beatmap upload).
- **First check is silent:** a player's first check (`online.MedalBaseline`) records the medals they already had as
  seen, so nobody gets a pile of old medals after the update.
- An unlock is never removed. A medal that's lost later (e.g. dropping out of the Top 100) and earned again doesn't
  pop up again. Restricted accounts don't collect unlocks.

## Original medals (`medals`, index 0-15)

The awarding rules are the `medco == N` checks in `getmedals()`. Stats come from the `User` row.

| # | Medal | Description shown | How to earn it | Hover hint (`MEDAL_HINTS`) |
|---|---|---|---|---|
| 0 | The End | You've made it | Global rank **#1** | Climb all the way to global rank #1. Nobody above you. Nobody. |
| 1 | Baby Steps | Welcome to the Game | More than **1 pp** | Earn your very first pp (more than 1). Everyone starts somewhere! |
| 2 | >~< | Impressive | Max combo over **1,000** | Chain a combo of over 1,000 without dropping it |
| 3 | Psycho | Dang you can read that?! | Clean clear* of a ranked Lv 30+ map with RND + DT at 1.5x or faster (`_former_coming_soon`) | Clear a ranked Lv 30+ difficulty with Random and Double Time at 1.5x or faster, 70%+ accuracy |
| 4 | Welcome back Veteran | Glad to see you back | Back after 30+ days away: recorded live by `welcome_back()` when the game reports a status (setstatus), or a 30+ day gap between their submitted plays | Come back and play after 30 days or more away |
| 5 | D-Ranker | Unrhythmic | More than **1,000 misses** in total | Miss over 1,000 notes in total. A badge of honour, honestly |
| 6 | S-Ranker | Like to show off. huh? | More than **1,000 Perfect hits** in total | Land over 1,000 Perfect hits in total |
| 7 | Supporter | Thanks for supporting Qlute! 💖 | An active supporter grant (`moderation.service.is_supporter`); checked right after `grant_support()` too. Was "Donator" (never obtainable) | Become a Qlute supporter (the Support page). Thank you <3 |
| 8 | Sniper | First Comes, First Serve! | First clean clear* on a ranked map that 2+ other players cleared later (by `Score.created`) | Be the first to clear a ranked map that at least 2 other players clear after you (70%+ accuracy) |
| 9 | BreakThrough | Unstoppable | +100 pp within 7 days in `stat_history` (the day before a player's first ranked play counts as 0 pp) | Gain 100 pp or more within 7 days |
| 10 | Top 100 | You are the chosen one | Global rank **100 or better** | Break into the global top 100 |
| 11 | Top 50 | Almost There | Global rank **50 or better** | Push your way into the global top 50 |
| 12 | Top 10 | Grab some Popcorn 🍿 | Global rank **10 or better** | Crack the global top 10 and enjoy the show |
| 13 | Top 1,000 | Still a Virgin at this game are you? | Global rank **1,000 or better** | Sneak into the global top 1,000 |
| 14 | Making the game better | You are making the community better! | On the Qlute team (`moderation.StaffMember`), `TEAM_MEDAL` | Join the Qlute team and help build the game |
| 15 | Team Moderator | Keeping Qlute fun and fair for everyone | Team member with the `mod` role, `MOD_MEDAL` | Become a Qlute moderator and keep the peace |

## Added medals (`EXTRA_MEDALS`, index 16-69)

Each entry is `(title, description, how to earn, rule key)`. The description is the flavour text (shown on the tile and
sent to the game); "how to earn" is the profile's hover hint. The rule for each key is in `_extra_medal_checks()`.

| # | Medal | Description | How to earn it (hover hint) | Rule key | Data used |
|---|---|---|---|---|---|
| 16 | Getting Hooked | Just one more map... right? | Submit 50 plays | `plays50` | `Score` rows for the player |
| 17 | No Life | Touch grass? Never heard of it | Submit 1,000 plays | `plays1000` | `Score` rows |
| 18 | Rising Star | Someone's been practising ✨ | Reach 100 pp | `pp100` | `User.ranked_points` |
| 19 | Elite | Your keyboard fears you | Reach 1,000 pp | `pp1000` | `User.ranked_points` |
| 20 | Seasoned | Halfway to triple digits! | Reach level 50 | `level50` | `levels.level(User.ranked_score)`; kept if earned under the old score / 2M levels |
| 21 | Centurion | Triple digits, baby! | Reach level 100 | `level100` | same (kept if earned before) |
| 22 | Flawless | Not a single hair out of place | SS a ranked map, every hit Perfect (no HT, NF or slowdowns) | `ss` | clean clears* |
| 23 | Unbreakable | Your combo has plot armour | Full combo a ranked Lv 30+ difficulty (no HT, NF or slowdowns) | `fc30` | clean clears* |
| 24 | Sharpshooter | Do you even miss? | Keep 98%+ overall accuracy over 50+ plays | `acc98` | `User.accuracy`, `Score` rows |
| 25 | Combo Monster | Om nom nom, combos | Hit a 3,000 combo | `combo3000` | `User.max_combo` |
| 26 | Deep End | No floaties allowed 🏊 | Clear a ranked Lv 50+ difficulty with 70%+ accuracy (no HT, NF or slowdowns) | `lv50` | clean clears* |
| 27 | Into the Abyss | It stared back. You didn't blink. | Clear a ranked Lv 70+ difficulty, the black ones, with 70%+ accuracy (no HT, NF or slowdowns) | `lv70` | clean clears* |
| 28 | Marathon | Your chair has your shape now | Play for 24 hours in total | `playtime24` | `User.playtime` (seconds) |
| 29 | Mapper | Making the notes instead of hitting them | Upload a beatmap set, or get an osu! claim accepted | `mapper` | `submissions.Submission.owner` |
| 30 | Ranked Mapper | Officially certified banger 🎶 | Own a beatmap set that gets ranked | `rankedmapper` | `Submission` + `Beatmap.ranked == 1` |
| 31 | Collector | Gotta favourite 'em all | Favourite 10 beatmap sets | `fav10` | `online.FavoriteBeatmap` |
| 32 | Social Butterfly | The more the merrier! 🦋 | Have 5 mutual friends (you've both added each other) | `friends5` | `online.Friend` |
| 33 | Critic | Everyone's a critic... and so are you | Post 10 comments on beatmaps | `comments10` | `online.BeatmapComment` |
| 34 | Oops | Did you even press anything? | Submit a play where every single note was a miss | `allmiss` | `Score` rows (any map, any mods) |
| 35 | So Close | One. Single. Miss. | Clear a ranked map with exactly one miss and 95%+ accuracy (no HT, NF or slowdowns) | `onemiss` | clean clears* |
| 36 | Speed Demon | Gotta go fast 💨 | Clear a ranked Lv 20+ difficulty with DT at 1.5x or faster, 70%+ accuracy | `speed15` | clean clears* + `Score.speed_multi` |
| 37 | Slowpoke | Taking it nice and slow 🐢 | Submit a play at 0.75x speed or slower | `slow` | `Score.speed_multi` |
| 38 | Big Leagues | Now we're talking | Reach 500 pp | `pp500` | `User.ranked_points` |
| 39 | Perfectionist | Ten out of ten, every time | SS 10 different ranked maps (no HT, NF or slowdowns) | `ss10` | clean clears* |
| 40 | Dedicated | Qlute is your second home | Submit 5,000 plays | `plays5000` | `Score` rows |
| 41 | Cheat Code | 30 lives? In this economy? | Type the Konami code (↑↑↓↓←→←→ B A) anywhere in the game | `client:konami` | game-reported† |
| 42 | Rage Quit | The keyboard had it coming | Quit a map from the pause menu after missing 20+ notes | `client:ragequit` | game-reported† |
| 43 | Pause Addict | Hold on, let me get a drink | Pause 10 times in one play | `client:pauses` | game-reported† |
| 44 | Night Owl | Sleep is for the weak 🦉 | Finish a play between 2 and 5 am (the player's own clock) | `client:nightowl` | game-reported† |
| 45 | Silent Disco | Who needs music anyway? | Finish a play with the game's music volume all the way down | `client:muted` | game-reported† |
| 46 | Doki Doki | Listening to Qlute's heartbeat 💓 | Keep the mouse on the main menu logo for 64 heartbeats | `client:heartbeat` | game-reported† |
| 47 | Warming Up | The keyboard's getting warm | Clear a ranked Lv 10+ difficulty with 70%+ accuracy (no HT, NF or slowdowns) | `pass10` | clean clears* |
| 48 | Finding the Rhythm | Tap tap tap, it's clicking | Clear a ranked Lv 20+ difficulty with 70%+ accuracy (no HT, NF or slowdowns) | `pass20` | clean clears* |
| 49 | Getting Serious | No more warm-up maps | Clear a ranked Lv 30+ difficulty with 70%+ accuracy (no HT, NF or slowdowns) | `pass30` | clean clears* |
| 50 | Over the Hill | It's all downhill from here. Right? | Clear a ranked Lv 40+ difficulty with 70%+ accuracy (no HT, NF or slowdowns) | `pass40` | clean clears* |
| 51 | Uncharted Waters | Here be dragons 🐉 | Clear a ranked Lv 60+ difficulty with 70%+ accuracy (no HT, NF or slowdowns) | `pass60` | clean clears* |
| 52 | Event Horizon | Even light can't escape these notes | Clear a ranked Lv 80+ difficulty with 70%+ accuracy (no HT, NF or slowdowns) | `pass80` | clean clears* |
| 53 | Beyond Reason | Your fingers have left the chat | Clear a ranked Lv 90+ difficulty with 70%+ accuracy (no HT, NF or slowdowns) | `pass90` | clean clears* |
| 54 | Summit | Nothing left to climb 🏔 | Clear a ranked Lv 100+ difficulty with 70%+ accuracy (no HT, NF or slowdowns) | `pass100` | clean clears* |
| 55 | Clean Sweep | Not a single note dropped | Full combo a ranked Lv 10+ difficulty (no HT, NF or slowdowns) | `fc10` | clean clears* |
| 56 | Steady Hands | Calm, cool, collected | Full combo a ranked Lv 20+ difficulty (no HT, NF or slowdowns) | `fc20` | clean clears* |
| 57 | Iron Focus | Blink and you'll miss it. You didn't. | Full combo a ranked Lv 40+ difficulty (no HT, NF or slowdowns) | `fc40` | clean clears* |
| 58 | Untouchable | The misses can't find you | Full combo a ranked Lv 50+ difficulty (no HT, NF or slowdowns) | `fc50` | clean clears* |
| 59 | Zero Gravity | Floating through the chaos | Full combo a ranked Lv 60+ difficulty (no HT, NF or slowdowns) | `fc60` | clean clears* |
| 60 | Abyss Walker | You walked out of the deep without a scratch | Full combo a ranked Lv 70+ difficulty (no HT, NF or slowdowns) | `fc70` | clean clears* |
| 61 | Perfect Storm | Thunder, lightning, zero misses ⚡ | Full combo a ranked Lv 80+ difficulty (no HT, NF or slowdowns) | `fc80` | clean clears* |
| 62 | Mythical | People will tell stories about this one | Full combo a ranked Lv 90+ difficulty (no HT, NF or slowdowns) | `fc90` | clean clears* |
| 63 | Absolute | There is nothing beyond this | Full combo a ranked Lv 100+ difficulty (no HT, NF or slowdowns) | `fc100` | clean clears* |
| 64 | Double Trouble | Twice the speed, twice the fun | Clear a ranked map with Double Time, 70%+ accuracy | `mod:DT` | ranked `Score` rows with the mod, 70%+ accuracy (HT / NF allowed) |
| 65 | Taking It Easy | Half the speed, all of the vibes | Clear a ranked map with Half Time, 70%+ accuracy | `mod:HT` | ranked `Score` rows with the mod, 70%+ accuracy (HT / NF allowed) |
| 66 | Shuffle Mode | Who put that note there? | Clear a ranked map with Random, 70%+ accuracy | `mod:RND` | ranked `Score` rows with the mod, 70%+ accuracy (HT / NF allowed) |
| 67 | Sliced and Diced | Chop chop 🔪 | Clear a ranked map with Slice, 70%+ accuracy | `mod:SL` | ranked `Score` rows with the mod, 70%+ accuracy (HT / NF allowed) |
| 68 | Lights Out | Who needs to see the notes anyway? | Clear a ranked map with Black-out, 70%+ accuracy | `mod:BT` | ranked `Score` rows with the mod, 70%+ accuracy (HT / NF allowed) |
| 69 | Safety Net | Failing is optional now | Clear a ranked map with No-Fail, 70%+ accuracy | `mod:NF` | ranked `Score` rows with the mod, 70%+ accuracy (HT / NF allowed) |

### †Game-reported medals (`CLIENT_MEDALS`)

Silly things only the game can see. The game sends `POST apiv2/medals/claim/<name>` (logged in) when it notices one;
the server records the unlock and replies with the medal, which the game pops up straight away. Earned = the
`online.MedalUnlock` row exists. Only names in `CLIENT_MEDALS` are accepted, and they're just for fun: nothing stops a
modified client from claiming them, so never hang anything that matters on them. The profile hover hints for these are
deliberately a bit cryptic. Game side: `Qlute/Script/Medals/MedalPopup.cs` (`Claim`, the Konami code), `PauseMenu.cs`,
`IntroPending.cs` and `ApiOperator.SS()`.

### \*Clean clears (`_medal_clears()`)

The server stores every submitted play but **can't tell a failed run from a pass**, and some mods make a map much
easier. So the skill medals (Flawless, Unbreakable, Deep End, Into the Abyss) only count a play when **all** of these hold:

- the score is on a **ranked** map (`Score.ranked == 1`) and the difficulty is ranked (`Beatmap.ranked == 1`)
- no **HT** (Half Time), **NF** (No Fail) or **AT** (Autoplay) in its mods (`MEDAL_BANNED_MODS`)
- speed **1.0× or faster** (`Score.speed_multi`)
- accuracy **70% or higher** (`MEDAL_MIN_ACCURACY`), which is C grade or better on the site's grading. This floor
  stands in for "passed", since fails aren't recorded

Accuracy uses the site's formula: `(Perfect + Great / 2 + Meh / 3) / total hits`.

Why: a player once got Deep End from a Lv 62 map played with HT at 0.7× and a Lv 59 map with 1,667 misses and 0 pp.
Neither was a real clear.

Ranked-only also stops anyone from uploading an easy joke map and SS-ing it for a medal.

## Categories (`MEDAL_CATEGORIES`)

The profile groups medals like this, easiest first inside each group; the APIs send each medal's `category`.

- **Progress**: Baby Steps, Getting Hooked, Rising Star, Big Leagues, Elite, Seasoned, Centurion, Marathon, No Life, Dedicated
- **Ranking**: Top 1,000, Top 100, Top 50, Top 10, The End
- **Skill**: >~<, Combo Monster, S-Ranker, Flawless, Perfectionist, So Close, Sharpshooter, D-Ranker, Oops, Sniper, BreakThrough, Psycho
- **Map level: Pass**: Warming Up, Finding the Rhythm, Getting Serious, Over the Hill, Deep End, Uncharted Waters, Into the Abyss, Event Horizon, Beyond Reason, Summit
- **Map level: Full combo**: Clean Sweep, Steady Hands, Unbreakable, Iron Focus, Untouchable, Zero Gravity, Abyss Walker, Perfect Storm, Mythical, Absolute
- **Mods**: Double Trouble, Taking It Easy, Shuffle Mode, Sliced and Diced, Lights Out, Safety Net, Speed Demon, Slowpoke
- **Community**: Mapper, Ranked Mapper, Collector, Social Butterfly, Critic, Welcome back Veteran
- **Team & support**: Supporter, Making the game better, Team Moderator
- **Secret**: Cheat Code, Rage Quit, Pause Addict, Night Owl, Silent Disco, Doki Doki

## Adding a medal

1. Append `("Title", "Playful description", "How to earn it", "rule_key")` to the end of `EXTRA_MEDALS`. Keep the
   description in the same joking voice as the others; the hint should still say exactly what to do.
2. Add `"rule_key": lambda: <condition>` to `checks` in `_extra_medal_checks()`. The lambdas are lazy and
   wrapped in `try`, so a broken rule only fails its own medal instead of the whole profile.
3. Restart daphne (`sudo systemctl restart daphne`). `views.py` is only reloaded on restart. Players who already
   qualify get the new medal's popup on their next check.
4. Add its title to a group in `MEDAL_CATEGORIES` (otherwise it shows under "Other").
5. Update this file.

Adding a game-reported medal: use rule key `"client:<name>"` (it lands in `CLIENT_MEDALS` by itself), then call
`MedalPopup.Claim("<name>")` from the game when it happens.

Cost: all 34 medals take about 35 ms per player (measured on the live database in Nov 2026).
