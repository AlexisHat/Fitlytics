"""The close-up on one detected interval, opened from the interval overview."""

from typing import Final

import polars as pl
import streamlit as st

from app.formatting import format_interval_type, format_minutes, format_optional
from intervals import (
    BlockDetail,
    IntervalBlock,
    block_detail,
    classify_block,
    slice_block,
)
from plots import plot_interval_detail

_BUTTONS_PER_ROW: Final = 6
"""How many interval buttons fit in one row before wrapping. A fixed count
rather than one column per block, so the buttons keep the same width on a
session with three repetitions and on one with twelve."""


def button_rows(count: int) -> list[list[int]]:
    """Split the interval numbers ``1..count`` into rows of buttons.

    Args:
        count: How many blocks were detected.

    Returns:
        The blocks' numbers grouped into rows, each at most
        :data:`_BUTTONS_PER_ROW` long; empty if nothing was detected.

    >>> button_rows(3)
    [[1, 2, 3]]
    >>> button_rows(8)
    [[1, 2, 3, 4, 5, 6], [7, 8]]
    >>> button_rows(0)
    []
    """
    numbers = list(range(1, count + 1))
    return [
        numbers[start : start + _BUTTONS_PER_ROW]
        for start in range(0, count, _BUTTONS_PER_ROW)
    ]


def _render_detail_metrics(block: IntervalBlock, detail: BlockDetail) -> None:
    """Render the block's figures as two rows of tiles, power then heart rate."""
    power_columns = st.columns(4)
    power_columns[0].metric("Ø Leistung", f"{block.avg_power_w:.0f} W")
    power_columns[1].metric("Maximum", f"{detail.max_power_w:.0f} W")
    power_columns[2].metric("Gleichmäßigkeit", f"{block.evenness:.2f}")
    power_columns[3].metric(
        "Ø Trittfrequenz", format_optional(detail.avg_cadence, "{:.0f} rpm")
    )

    heart_columns = st.columns(3)
    heart_columns[0].metric(
        "Ø Herzfrequenz", format_optional(block.avg_heart_rate, "{:.0f} bpm")
    )
    heart_columns[1].metric(
        "Puls Start",
        format_optional(detail.heart_rate_start, "{:.0f} bpm"),
    )
    heart_columns[2].metric(
        "Puls Ende",
        format_optional(detail.heart_rate_end, "{:.0f} bpm"),
        delta=format_optional(block.heart_rate_drift_bpm, "{:+.1f} bpm"),
        delta_color="off",
    )


@st.dialog("Intervall im Detail", width="large")
def _show_interval_dialog(
    series: pl.DataFrame,
    block: IntervalBlock,
    number: int,
    target_power_w: int | None,
) -> None:
    """Open the modal showing one block's own curves and figures.

    A modal rather than another section below the overview: the athlete
    comes here to compare one repetition against the others, and jumping
    back and forth is only quick if closing the close-up puts the overview
    back exactly as it was.

    Args:
        series: The workout's full 1 Hz series the block was detected on.
        block: The block to show.
        number: The block's position in the session, counting from 1, used
            as its heading.
        target_power_w: The planned power for the session, or None if the
            athlete gave no plan.
    """
    type_label = format_interval_type(classify_block(block))
    st.markdown(
        f"**Intervall {number}** — {format_minutes(block.duration)} · {type_label}"
    )
    block_series = slice_block(series, block)
    _render_detail_metrics(block, block_detail(block_series))
    st.pyplot(plot_interval_detail(block_series, block, target_power_w))


def render_interval_buttons(
    series: pl.DataFrame,
    blocks: list[IntervalBlock],
    target_power_w: int | None,
    key_prefix: str,
) -> None:
    """Render one button per detected block, each opening its close-up.

    Buttons rather than a persistent selection widget: a button is true
    only on the rerun that follows the click, so closing the modal leaves
    nothing selected. A selectbox or segmented control would still hold the
    block after the modal closed and reopen it on the next rerun.

    Args:
        series: The workout's full 1 Hz series the blocks were detected on.
        blocks: The detected blocks, in chronological order. An empty list
            renders nothing.
        target_power_w: The planned power for the session, or None if the
            athlete gave no plan.
        key_prefix: Prefix for the buttons' widget keys, unique per
            workout — a day may hold more than one.
    """
    if not blocks:
        return

    st.caption("Einzelnes Intervall genauer ansehen:")
    for row in button_rows(len(blocks)):
        columns = st.columns(_BUTTONS_PER_ROW)
        for column, number in zip(columns, row, strict=False):
            if column.button(
                f"Intervall {number}",
                key=f"{key_prefix}_interval_detail_{number}",
                width="stretch",
            ):
                _show_interval_dialog(
                    series, blocks[number - 1], number, target_power_w
                )
