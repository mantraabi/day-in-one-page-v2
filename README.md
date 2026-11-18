# 17 November 2026 — one day, one page

[![built for make.fun](https://make.fun/badge/news-image-20261117.svg)](https://make.fun/c/news-image-20261117?utm_source=github&utm_medium=readme&utm_campaign=news-image-20261117)

A single 1024×1024 newspaper front page for 17 November 2026. The lead story
is the second day of strikes on the bridge over the Kerch Strait, drawn as an
original vector illustration: one deck running away from the viewer, a span
blown out of it, the piece lying in the water, smoke off the break. Below the
fold sit six story cards, eight one-line briefs and a strip of the day's
figures — fifteen stories in total, all from the competition brief.

Everything is drawn with Pillow. There are no photographs, no third-party
artwork, no logos.

## Regenerate

Two steps. The first one touches the network; the second one does not.

    python3 tools/prepare_land.py --fetch
    python3 main.py

`prepare_land.py --fetch` downloads the Natural Earth 1:50m land polygons once,
simplifies the rings and caches them in `tools/land.json`. After that the
renderer is fully offline: `tools/gen_poster.py` reads the cache, and `main.py`
writes `entry.png` into `$MAKEFUN_OUTPUT_DIR` (default `out/`).

The render is deterministic — same input, byte-identical output — and draws at
three times the final size before a single LANCZOS downsample, so the 1px rules
and the small caps stay crisp.

## Requirements

Python 3 and Pillow. Nothing else at render time.

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
