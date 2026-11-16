# pp v3 and competitive score

Implemented twice, kept bit-identical:

- Server (authoritative): `Chikara/Chikara/ppv2calc.py`. `/Storage/regen/ppv2calc.py` is a symlink to it.
- Client (preview): `Qlute/Script/Gameplay/PerformanceCalculator.cs`.

Change the constants in both files together. A cross-check over 168 synthetic plays (all mods, custom speeds, Random) matched bit for bit.

## Score: 0 to 1,000,000 on NoMod, scaled by the mod multiplier

```
base     = 900,000 × accuracy + 100,000 × combo − 900,000 × misses / notes
score    = round( max(0, base) × multiplier )
accuracy = (10·perfect + 7·great + 3·meh) / (10·notes)        (1, 0.7, 0.3, 0)
combo    = Σ_hits weight · min(combo after hit, 400)  /  10 · Σ_{i=1..notes} min(i, 400)
```

- All Perfect = **1,000,000**, all Great = **700,000**, all Meh = **300,000** on NoMod.
- Every miss takes off one Perfect note's accuracy value (900,000 / notes). The score never goes below 0. The in-game score visibly drops on a miss.

- An SS on NoMod is exactly **1,000,000**. With DT 1.25× it is 1,150,000, with NF 500,000.
- The combo part breaks ties between plays with equal accuracy. Because combo stops counting at 400, one miss costs about the same anywhere after the first 400 notes. A miss also loses combo on top of its own penalty.
- Everything is integer until two divisions, so the client and the server agree to the point.
- Map leaderboards are ordered by score. When two scores tie, the one set first ranks higher.
- Each player keeps one row per map: their best by score (the osu!-stable rule). A worse play never replaces a better one.

### Score multipliers

| Mod | × |
| --- | --- |
| Rate (DT/HT/custom) | `1 + 0.6·(rate−1)` above 1×, `max(0.1, 1 − 1.4·(1−rate))` below 1×. 1.25× gives 1.15, 1.5× gives 1.30, 0.75× gives 0.65, 0.5× gives 0.30 |
| NF | 0.50 |
| SL | 1.05 |
| BT | 1.15 |
| AM | 0.50 |
| RND | 1.00 |

The rate is rounded to 0.01. The old formula paid **less** than NoMod for speeds between 1.0× and 1.087× and differed between files. This one is continuous and the same everywhere.

## pp

**Star rating** comes from a strain model on rate-adjusted times, so DT and HT change the difficulty itself.

- Each note decays every column's strain by `0.125^Δt` and the overall strain by `0.30^Δt` (Δt in seconds since the previous note).
- The note then adds 2 to its own column's strain (jacks) and 1 to the overall strain (density and chords).
- The highest strain in each 400 ms section is kept. The sorted peaks are summed as `Σ peak_k · 0.9^k`, then `× 0.028`.
- Random never changes the rating, because it is computed from the map's real columns.

**Max pp (SS):** `1.243 · max(stars − 0.15, 0.05)^2.8 · (1 + 0.15·min(1, notes/2000)) · modFactor`

- The length bonus is capped at +15%, so long maps can't be farmed.
- modFactor: NF 0.90, SL 1.04, BT 1.08, AM 0.50. Rate mods have no factor here because they already change the stars.

**Play pp:** `maxPP · 0.999^(greats·k) · 0.995^(mehs·k) · 0.98^(misses·k)`, with `k = min(1, 1000/notes)`

- Each Great costs a little (0.1%), each Meh more (0.5%) and each miss the most (2%). `k` makes the penalties lighter on maps longer than 1000 notes.
- On a 1000-note map: 50 greats = 95% of max, 20 mehs = 90%, 5 misses = 90%, all greats = 37%.

- Only the counts matter. The old rule divided **all** pp earned so far by 1.2 on every miss, so late misses cost far more than early ones and runs varied wildly.
- Notes that never got judged count as misses.

Calibration: Hommarju - Slluuddggee (ShibePlanet) [Slliimmee] rates 5.34★; with the original 1.13 scale its SS was 124pp, its osu!mania value. It now pays 10% more (1.243). Reference values (2000+ notes): 3★ ≈ 26pp, 4★ ≈ 63pp, 5★ ≈ 119pp, 6★ ≈ 201pp, 7★ ≈ 312pp, 8★ ≈ 458pp, 10★ ≈ 865pp. Change `PP_SCALE` (server) and `PpScale` (client) together to rescale everything.

**Player pp:** `Σ pp_i · 0.95^i` over the best 100 plays, one per map. This used to be linear `1 − 0.02·i` over 50. Player accuracy uses the same weights.

## Map level (1–100)

`level = 1 + 99 · ((ssPP − 5.5) / 1644.5)^0.8`, truncated, with no clamping (the game's `LevelFromPp`, mirrored exactly by `level_from_pp`). Below 5.5pp a map is Lv 0 (the game's C# gives NaN there, which .NET turns into 0), exactly 5.5pp is Lv 1, 1,650pp is Lv 100 and harder maps keep going. The bounds were scaled with the +10% pp boost, so every map keeps the level it had. Stored levels were recomputed by migration `dbview/0011_recompute_levels`. Lv 7 ≈ 55–65pp, Lv 10 ≈ 90–100pp, Lv 50 ≈ 690pp. It uses the map's NoMod SS pp (`level_from_pp` / `LevelFromPp`) and is stored in `beatmaps.Level`. In song select, mods change the pp the level is computed from, so it stays within 1–100.

## Integrity

- The server re-plays every replay. Judgement counts, max combo, pp and score all come from that re-play, not from the client's headers. Mismatches are logged as `[pp] mismatch`.
- Auto-restrict guard: a single ranked play worth more than `max(25% of the player's pp, 600pp)` restricts the player. The old floor of 120pp would have banned new players on the new scale. The values are `PP_JUMP_RATIO` and `PP_JUMP_FLOOR` in views.py.

## Rollout

1. `python manage.py migrate dbview` adds `scores.score` and an index on (beatmap, ranked, score).
2. `python -m Chikara.recalc_ppv3 --dry-run`, check the summary, then run it without `--dry-run` (optionally with `--jobs 8`). This re-rates every map, re-plays every stored replay and recomputes every player. Scores without a replay keep their legacy score and get 0 pp.
3. Ship the client build. Its beatmap cache version was bumped, so song-select pp is recomputed on first launch.

`rebuildpp.py` and `rebuildscores.py` now exit with a pointer to `recalc_ppv3.py`.
