#!/usr/bin/env python3
"""Graded entrypoint for the make.fun news-image entry (news-image-20261117).

Authoring time vs. grading time
-------------------------------
The poster is *rendered* at authoring time by ``tools/gen_poster.py``, which
imports Pillow (``from PIL import Image, ...``).  That script is the generator:
it produced the committed ``entry.png`` sitting next to this file, and it stays
in the repository to document how the image was drawn.

The graded entrypoint is this file, and it must run under a much poorer
runtime than the authoring machine:

    python3 -P -s /bot/main.py

in a container with no network, the repository bind-mounted *read-only* at
``/bot``, an empty writable ``/output``, ``TZ=UTC``, ``PYTHONHASHSEED=0``,
``LANG=C.UTF-8``, an unprivileged user, 1 CPU, 512 MB RAM and 60 s wall time.
That image has **no third-party packages installed** — no Pillow, no numpy,
nothing.  Any ``import PIL`` there raises ImportError before a single pixel is
drawn, the process exits 1, and the run is scored as a failure.

So this file imports the standard library only.  It does not render anything:
it reads the committed, already-rendered ``entry.png``, checks that the bytes
really are the poster we expect by parsing the PNG signature and the IHDR chunk
with ``struct`` (no Pillow needed for that), and copies those exact bytes to
``$MAKEFUN_OUTPUT_DIR/entry.png``.  The pixels are never touched here; they were
fixed at authoring time.

Validation refuses loudly with a clear message on stderr and exit status 1 if
the committed file is not a genuine PNG, is not 1024x1024, is not 8-bit, or is
not under 1 MiB.

Usage:

    python3 main.py                                    # writes ./out/entry.png
    MAKEFUN_OUTPUT_DIR=/output python3 main.py         # what the grader does

Standard library only: hashlib, json, os, struct, sys, zlib.
"""

import hashlib
import json
import os
import struct
import sys
import zlib

# The poster is graded at exactly this size.
REQUIRED_WIDTH = 1024
REQUIRED_HEIGHT = 1024
# Grading ceiling for the delivered file.
MAX_BYTES = 1024 * 1024

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
IHDR_LENGTH = 13  # IHDR payload is always 13 bytes: 2 x uint32 + 5 x uint8

# PNG colour types defined by the spec.  Type 3 (palette) carries 8-bit
# indices, so it is a legal 8-bit image in the sense used here.
VALID_COLOUR_TYPES = frozenset({0, 2, 3, 4, 6})

HERE = os.path.dirname(os.path.abspath(__file__))
COMMITTED_PNG = os.path.join(HERE, "entry.png")


class InvalidPoster(Exception):
    """The committed entry.png is not the image we are willing to ship."""


def read_ihdr(data):
    """Parse the PNG signature and IHDR chunk with struct.  No Pillow.

    Returns (width, height, bit_depth).  Raises InvalidPoster with a
    human-readable reason if the bytes are not a real PNG of the required
    shape.
    """
    if len(data) < 8 + 8 + IHDR_LENGTH + 4:
        raise InvalidPoster(
            "file is %d bytes, too short to contain an 8-byte PNG signature "
            "and a 13-byte IHDR chunk" % len(data)
        )

    if data[:8] != PNG_SIGNATURE:
        raise InvalidPoster(
            "bad PNG signature: first 8 bytes are %r, expected %r"
            % (data[:8], PNG_SIGNATURE)
        )

    # First chunk after the signature must be IHDR: [length][type][data][crc].
    chunk_length, chunk_type = struct.unpack(">I4s", data[8:16])
    if chunk_type != b"IHDR":
        raise InvalidPoster(
            "first chunk is %r, expected b'IHDR' (the PNG header chunk)"
            % chunk_type
        )
    if chunk_length != IHDR_LENGTH:
        raise InvalidPoster(
            "IHDR chunk declares %d bytes, expected %d"
            % (chunk_length, IHDR_LENGTH)
        )

    # Refuse a corrupted header rather than trusting it: CRC covers the chunk
    # type and its payload.
    crc_stored = struct.unpack(">I", data[29:33])[0]
    crc_actual = zlib.crc32(data[12:29]) % (2 ** 32)
    if crc_stored != crc_actual:
        raise InvalidPoster(
            "IHDR CRC mismatch: chunk says 0x%08x, computed 0x%08x"
            % (crc_stored, crc_actual)
        )

    (width, height, bit_depth, colour_type, compression, filt, interlace) = (
        struct.unpack(">IIBBBBB", data[16:29])
    )

    if (width, height) != (REQUIRED_WIDTH, REQUIRED_HEIGHT):
        raise InvalidPoster(
            "image is %dx%d, required %dx%d"
            % (width, height, REQUIRED_WIDTH, REQUIRED_HEIGHT)
        )
    if bit_depth != 8:
        raise InvalidPoster("bit depth is %d, required 8" % bit_depth)
    if colour_type not in VALID_COLOUR_TYPES:
        raise InvalidPoster(
            "colour type is %d, not a defined PNG colour type %s"
            % (colour_type, sorted(VALID_COLOUR_TYPES))
        )
    # Baseline PNG settings; anything else is not the file we rendered.
    if (compression, filt, interlace) != (0, 0, 0):
        raise InvalidPoster(
            "not a baseline PNG: compression=%d filter=%d interlace=%d, "
            "expected 0/0/0" % (compression, filt, interlace)
        )

    return width, height, bit_depth


def main():
    try:
        with open(COMMITTED_PNG, "rb") as handle:
            data = handle.read()
    except OSError as exc:
        print(
            "error: cannot read the committed poster %s: %s" % (COMMITTED_PNG, exc),
            file=sys.stderr,
        )
        return 1

    try:
        if len(data) >= MAX_BYTES:
            raise InvalidPoster(
                "file is %d bytes, must be under 1 MiB (%d bytes)"
                % (len(data), MAX_BYTES)
            )
        width, height, _bit_depth = read_ihdr(data)
    except InvalidPoster as exc:
        print("error: %s: %s" % (COMMITTED_PNG, exc), file=sys.stderr)
        return 1

    digest = hashlib.sha256(data).hexdigest()

    out_dir = os.environ.get("MAKEFUN_OUTPUT_DIR") or "out"
    if not os.path.isabs(out_dir):
        out_dir = os.path.join(HERE, out_dir)
    target = os.path.join(out_dir, "entry.png")

    try:
        os.makedirs(out_dir, exist_ok=True)
        with open(target, "wb") as handle:
            handle.write(data)
    except OSError as exc:
        print(
            "error: cannot write %s: %s" % (target, exc),
            file=sys.stderr,
        )
        return 1

    written = os.path.getsize(target)
    if written != len(data):
        print(
            "error: wrote %d bytes to %s, expected %d"
            % (written, target, len(data)),
            file=sys.stderr,
        )
        return 1

    summary = {
        "output": target,
        "width": width,
        "height": height,
        "bytes": written,
        "sha256": digest,
    }
    print(json.dumps(summary, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
