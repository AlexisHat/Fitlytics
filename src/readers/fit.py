"""Import a single training session from a FIT file."""

from itertools import pairwise
from pathlib import Path
from typing import IO, Any

import deal
import fitdecode
from pydantic import ValidationError as PydanticValidationError

from errors import FileImportError
from models import RecordPoint, Workout


def _build_record_point(fields: dict[str, Any]) -> RecordPoint:
    """Build a RecordPoint from a FIT ``record`` message's raw fields.

    Prefers the higher-precision ``enhanced_speed``/``enhanced_altitude``
    fields (more range and resolution than the older plain fields) over
    their plain counterparts when both are present.

    Args:
        fields: Raw field values of a single ``record`` message, keyed by
            FIT field name.

    Returns:
        The corresponding RecordPoint.

    Raises:
        KeyError: If ``timestamp`` is missing.
        pydantic.ValidationError: If a present field has an unusable value.

    >>> from datetime import UTC, datetime
    >>> point = _build_record_point(
    ...     {
    ...         "timestamp": datetime(2026, 7, 16, 14, 11, 39, tzinfo=UTC),
    ...         "heart_rate": 120,
    ...     }
    ... )
    >>> point.heart_rate, point.power
    (120, None)
    """
    speed_ms = fields.get("enhanced_speed")
    if speed_ms is None:
        speed_ms = fields.get("speed")

    altitude_m = fields.get("enhanced_altitude")
    if altitude_m is None:
        altitude_m = fields.get("altitude")

    return RecordPoint(
        timestamp=fields["timestamp"],
        heart_rate=fields.get("heart_rate"),
        power=fields.get("power"),
        cadence=fields.get("cadence"),
        distance_m=fields.get("distance"),
        speed_ms=speed_ms,
        altitude_m=altitude_m,
    )


@deal.raises(FileImportError)
@deal.post(lambda result: len(result.records) >= 1)
@deal.post(lambda result: len(result.sport) > 0)
@deal.post(
    lambda result: all(a.timestamp <= b.timestamp for a, b in pairwise(result.records))
)
def import_fit_file(source: str | Path | IO[bytes]) -> Workout:
    """Import a single training session from a FIT file.

    Args:
        source: A filesystem path, or a file-like object such as
            Streamlit's ``UploadedFile`` returned by ``st.file_uploader()``.

    Returns:
        The imported workout with its time-ordered records.

    Raises:
        FileImportError: If the file cannot be read, is not a valid FIT
            file, does not contain exactly one session, or has no usable
            session/record data.
    """
    sessions: list[dict[str, Any]] = []
    records: list[RecordPoint] = []

    try:
        with fitdecode.FitReader(source) as reader:
            for frame in reader:
                if not isinstance(frame, fitdecode.FitDataMessage):
                    continue

                fields = {field.name: field.value for field in frame.fields}
                if frame.name == "session":
                    sessions.append(fields)
                elif frame.name == "record":
                    records.append(_build_record_point(fields))

        if len(sessions) != 1:
            raise FileImportError(
                f"expected exactly one session message, found {len(sessions)}"
            )
        session = sessions[0]

        if not session.get("sport"):
            raise FileImportError("session message has no sport")

        for earlier, later in pairwise(records):
            if earlier.timestamp > later.timestamp:
                raise FileImportError("records are not in chronological order")

        return Workout(
            start_time=session["start_time"],
            sport=session["sport"],
            sub_sport=session.get("sub_sport"),
            ftp_watts=session.get("threshold_power"),
            records=records,
        )
    except (fitdecode.FitError, OSError, KeyError, PydanticValidationError) as exc:
        raise FileImportError(f"could not import FIT file: {exc}") from exc
