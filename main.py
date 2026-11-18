#!/usr/bin/env python3
"""Entry point for the make.fun news-image entry (news-image-20261117).

Renders the 1024x1024 front page and writes entry.png into $MAKEFUN_OUTPUT_DIR
(default: ./out).  No network, no fonts beyond the Liberation family, no
dependencies beyond Pillow.

    python3 main.py
"""

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "tools"))

import gen_poster  # noqa: E402  (path set above)


def main():
    out_dir = os.environ.get("MAKEFUN_OUTPUT_DIR") or "out"
    if not os.path.isabs(out_dir):
        out_dir = os.path.join(HERE, out_dir)
    os.makedirs(out_dir, exist_ok=True)

    image = gen_poster.build()
    target = os.path.join(out_dir, "entry.png")
    image.save(target, format="PNG", optimize=True)

    size_bytes = os.path.getsize(target)
    summary = {
        "output": target,
        "width": image.size[0],
        "height": image.size[1],
        "bytes": size_bytes,
        "under_1mib": size_bytes < 1024 * 1024,
    }
    print(json.dumps(summary, sort_keys=True))
    return 0 if summary["under_1mib"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
