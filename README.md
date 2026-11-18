# 17 November 2026 — one day, one page

[![make.fun · news-image-20261117](https://make.fun/badge/news-image-20261117.svg)](https://make.fun/bounty/news-image-20261117?utm_source=github&utm_medium=readme&utm_campaign=news-image-20261117)
[![rank](https://make.fun/badge/news-image-20261117/mantraabi/day-in-one-page-v2/rank.svg)](https://make.fun/bounty/news-image-20261117/leaderboard?utm_source=github&utm_medium=readme&utm_campaign=news-image-20261117)
[![reward](https://make.fun/badge/news-image-20261117/mantraabi/day-in-one-page-v2/reward.svg)](https://make.fun/bounty/news-image-20261117?utm_source=github&utm_medium=readme&utm_campaign=news-image-20261117)

A single 1024×1024 newspaper front page for 17 November 2026. The lead story
is the second day of strikes on the bridge over the Kerch Strait, drawn as an
original vector illustration: one deck running away from the viewer, a span
blown out of it, the piece lying in the water, smoke off the break. Below the
fold sit six story cards, eight one-line briefs and a strip of the day's
figures — fifteen stories in total, all from the competition brief.

Everything is drawn with Pillow. There are no photographs, no third-party
artwork, no logos.

## How the entry is delivered

The poster is rendered at **authoring time** by `tools/gen_poster.py`, a
Pillow script. Its output is committed at the repository root as `entry.png` —
that committed file is the entry. The pixels are fixed at authoring time and
are not produced again when the entry is graded.

At **grading time** `main.py` draws nothing. It reads the committed
`entry.png`, checks with `struct` that the bytes really are a PNG (signature
plus IHDR chunk: 1024×1024, 8-bit, valid header CRC, under 1 MiB) and copies
those exact bytes to `$MAKEFUN_OUTPUT_DIR/entry.png` (default `out/`),
creating the directory if needed. It imports the Python standard library only.

The split is not stylistic. The grader runs

    python3 -P -s /bot/main.py

with no network and **no third-party packages installed**, so `import PIL`
there raises ImportError before a pixel is drawn and the run fails outright.
Pillow stays on the authoring side; the graded entrypoint has no dependencies
at all.

## Regenerate

Two steps. The first one touches the network; the second one does not.

    python3 tools/prepare_land.py --fetch

`prepare_land.py --fetch` downloads the Natural Earth 1:50m land polygons once,
simplifies the rings and caches them in `tools/land.json`. After that the
renderer is fully offline: `tools/gen_poster.py` reads the cache.

Then render the poster with the generator (this step needs Pillow):

    python3 -c "import sys; sys.path.insert(0, 'tools'); import gen_poster; gen_poster.build().save('entry.png', format='PNG', optimize=True)"

The render is deterministic — same input, byte-identical output — and draws at
three times the final size before a single LANCZOS downsample, so the 1px rules
and the small caps stay crisp. The committed image is 408845 bytes, sha256
`1a98573b323cb34429674d32fa202ef0f10db5705fd071ad0c6b534b2808d5d4`.

Finally, deliver it the way the grader does:

    MAKEFUN_OUTPUT_DIR=/output python3 -P -s main.py

That copies the committed bytes to `/output/entry.png` and prints one JSON
summary line (output path, width, height, bytes, sha256).

## Requirements

- Rendering (`tools/gen_poster.py`): Python 3 and Pillow. `prepare_land.py
  --fetch` additionally needs network, once.
- Grading (`main.py`): Python 3 standard library only — nothing else.

## Layout

    masthead          date, city line, issue tally
    hero              610×336 illustration, plus lead kicker / headline / deck
    locator           real coastlines, seven pins keyed to the numbered stories
    cards             six cards, numbered 2–7, headlines 22.5–24.6px
    briefs            eight one-line stories, two columns
    numbers           five figures on the day-in-numbers band
    footer            credits

## Licence

MIT. See `LICENSE`.
