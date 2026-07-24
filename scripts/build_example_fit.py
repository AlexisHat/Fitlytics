"""Build a small, valid example FIT file from a real private recording.

So that we have a small test case .fit file for testing we isolate about
20 records from a whole real trainings Session

Run from the repository root: ``uv run python scripts/build_example_fit.py``
"""

from pathlib import Path

import fitdecode
from fitdecode.utils import compute_crc

SRC = Path("data/private/07-162x8minFTP.fit")
DST = Path("data/beispiel/training_gueltig.fit")

N_RECORDS = 20
PREFIX_END = 134  # frames[0:134]: header .. 20th record (inclusive)
TAIL_START = 5600  # lap definition
TAIL_END = 5611  # exclusive; leaves out the original CRC frame (5611)


def main() -> None:
    """Read the private FIT file and write the trimmed example fixture."""
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
    new_file_bytes = new_header + body_bytes + footer_crc.to_bytes(2, "little")

    DST.parent.mkdir(parents=True, exist_ok=True)
    DST.write_bytes(new_file_bytes)
    print(f"written: {DST} ({len(new_file_bytes)} bytes, source {SRC.stat().st_size})")


if __name__ == "__main__":
    main()
