"""Build small example FIT files (valid, empty, broken) from a real recording.

The valid fixture takes a contiguous prefix (header through the 20th
``record`` message, so no local message type definition is ever skipped)
plus the closing summary messages (lap/event/session/activity, each with its
own definition message right before it) from the end of the file. A naive
middle "window" of records was tried first and rejected: FIT devices can
redefine a message's field layout mid-recording (e.g. once GPS lock is
acquired), so splicing in records from later in the file without their
locally-active definition breaks decoding.

Run from the repository root: ``uv run python scripts/build_example_fit.py``
"""

from pathlib import Path

import fitdecode
from fitdecode.utils import compute_crc

SRC = Path("data/beispiel/fit/07-162x8minFTP.fit")
DST_VALID = Path("data/beispiel/fixtures/training_gueltig.fit")
DST_EMPTY = Path("data/beispiel/fixtures/training_leer.fit")
DST_BROKEN = Path("data/beispiel/fixtures/training_defekt.fit")

N_RECORDS = 20
PREFIX_END = 134  # frames[0:134]: header .. 20th record (inclusive)
TAIL_START = 5600  # lap definition
TAIL_END = 5611  # exclusive; leaves out the original CRC frame (5611)


def build_valid_fixture() -> bytes:
    """Build the small, valid example FIT file's bytes."""
    with fitdecode.FitReader(str(SRC), keep_raw_chunks=True) as reader:
        frames = list(reader)

    header_bytes = frames[0].chunk.bytes
    body_frames = frames[1:PREFIX_END] + frames[TAIL_START:TAIL_END]
    body_bytes = b"".join(f.chunk.bytes for f in body_frames)

    new_header12 = bytearray(header_bytes[:12])
    new_header12[4:8] = len(body_bytes).to_bytes(4, "little")
    header_crc = compute_crc(bytes(new_header12), start=0, end=12)
    new_header = bytes(new_header12) + header_crc.to_bytes(2, "little")

    full_size = len(new_header) + len(body_bytes)
    footer_crc = compute_crc(new_header + body_bytes, start=0, end=full_size)
    return new_header + body_bytes + footer_crc.to_bytes(2, "little")


def main() -> None:
    """Write the valid, empty and broken example FIT fixtures."""
    valid_bytes = build_valid_fixture()
    DST_VALID.parent.mkdir(parents=True, exist_ok=True)
    DST_VALID.write_bytes(valid_bytes)
    src_size = SRC.stat().st_size
    print(f"written: {DST_VALID} ({len(valid_bytes)} bytes, source {src_size})")

    DST_EMPTY.write_bytes(b"")
    print(f"written: {DST_EMPTY} (0 bytes)")

    # Nur die ersten 20 Bytes: unvollstaendiger Header, garantiert ein Parse-Fehler.
    broken_bytes = valid_bytes[:20]
    DST_BROKEN.write_bytes(broken_bytes)
    print(f"written: {DST_BROKEN} ({len(broken_bytes)} bytes)")


if __name__ == "__main__":
    main()
