# Medals

Medals are not stored anywhere. They are worked out live from a player's stats every time someone asks, so a player
gets a medal the moment they qualify (and loses it if they stop qualifying, e.g. dropping out of the Top 100).

- **Code:** `Chikara/views.py`: `medals` (the original 16), `EXTRA_MEDALS` (the 18 added later),
  `getmedals()`, `_extra_medal_checks()` and `_medal_clears()`.
- **Where they show up:** the profile page (`views.user()`, "Medals · N / 34 earned"), the classic profile, the public
  profile JSON (`public_profile()`, `"medals"`), and the game's `listmedal/<username>` API
  (`[{"title", "desc", "achieved"}]`).
- **Hover hints:** on the profile, hovering a medal (or tapping it on a phone) shows how to earn it, prefixed with
  "Got it!" once earned. The text is `MEDAL_HINTS` for the original medals and the "how to earn" field of
  `EXTRA_MEDALS`. Styles are in `static/css/profile.css` (`.pf-medal::after`).
- **Order matters.** Both the original medals and the game client go by position in the list, so new medals are
  always **appended** to the end. Never insert or reorder.

## Original medals (`medals`, index 0-15)

The awarding rules are the `medco == N` checks in `getmedals()`. Stats come from the `User` row.

| # | Medal | Description shown | How to earn it | Hover hint (`MEDAL_HINTS`) |
|---|---|---|---|---|
| 0 | The End | You've made it | Global rank **#1** | Climb all the way to global rank #1. Nobody above you. Nobody. |
| 1 | Baby Steps | Welcome to the Game | More than **1 pp** | Earn your very first pp (more than 1). Everyone starts somewhere! |
| 2 | >~< | Impressive | Max combo over **1,000** | Chain a combo of over 1,000 without dropping it |
| 3 | Psycho | Dang you can read that?! | **Not obtainable.** The check (`points > 1000`) is hard-coded to never award it | Coming soon™. Even the devs don't know how yet 👀 |
| 4 | Welcome back Veteran | Glad to see you back | **Not obtainable.** No rule | Coming soon™. Pack your bags, veteran |
| 5 | D-Ranker | Unrhythmic | More than **1,000 misses** in total | Miss over 1,000 notes in total. A badge of honour, honestly |
| 6 | S-Ranker | Like to show off. huh? | More than **1,000 Perfect hits** in total | Land over 1,000 Perfect hits in total |
| 7 | Donator | Thanks for Supporting the Game! | **Not obtainable.** `donator` is always 0 | Coming soon™. Thank-you gifts are on their way |
| 8 | Sniper | First Comes, First Serve! | **Not obtainable.** No rule | Coming soon™. Keep your sights steady |
| 9 | BreakThrough | Unstoppable | **Not obtainable.** No rule | Coming soon™. The wall hasn't been built yet |
| 10 | Top 100 | You are the chosen one | Global rank **100 or better** | Break into the global top 100 |
| 11 | Top 50 | Almost There | Global rank **50 or better** | Push your way into the global top 50 |
| 12 | Top 10 | Grab some Popcorn 🍿 | Global rank **10 or better** | Crack the global top 10 and enjoy the show |
| 13 | Top 1,000 | Still a Virgin at this game are you? | Global rank **1,000 or better** | Sneak into the global top 1,000 |
| 14 | Making the game better | You are making the community better! | On the Qlute team (`moderation.StaffMember`), `TEAM_MEDAL` | Join the Qlute team and help build the game |
| 15 | Team Moderator | Keeping Qlute fun and fair for everyone | Team member with the `mod` role, `MOD_MEDAL` | Become a Qlute moderator and keep the peace |

## Added medals (`EXTRA_MEDALS`, index 16-33)

Each entry is `(title, description, how to earn, rule key)`. The description is the flavour text (shown on the tile and
sent to the game); "how to earn" is the profile's hover hint. The rule for each key is in `_extra_medal_checks()`.

| # | Medal | Description | How to earn it (hover hint) | Rule key | Data used |
|---|---|---|---|---|---|
| 16 | Getting Hooked | Just one more map... right? | Submit 50 plays | `plays50` | `Score` rows for the player |
| 17 | No Life | Touch grass? Never heard of it | Submit 1,000 plays | `plays1000` | `Score` rows |
| 18 | Rising Star | Someone's been practising ✨ | Reach 100 pp | `pp100` | `User.ranked_points` |
| 19 | Elite | Your keyboard fears you | Reach 1,000 pp | `pp1000` | `User.ranked_points` |
| 20 | Seasoned | Halfway to triple digits! | Reach level 50 | `level50` | `User.ranked_score × leveltemp` |
| 21 | Centurion | Triple digits, baby! | Reach level 100 | `level100` | same |
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

## Adding a medal

1. Append `("Title", "Playful description", "How to earn it", "rule_key")` to the end of `EXTRA_MEDALS`. Keep the
   description in the same joking voice as the others; the hint should still say exactly what to do.
2. Add `"rule_key": lambda: <condition>` to `checks` in `_extra_medal_checks()`. The lambdas are lazy and
   wrapped in `try`, so a broken rule only fails its own medal instead of the whole profile.
3. Restart daphne (`sudo systemctl restart daphne`). `views.py` is only reloaded on restart.
4. Update this file.

Cost: all 34 medals take about 35 ms per player (measured on the live database in Nov 2026).
