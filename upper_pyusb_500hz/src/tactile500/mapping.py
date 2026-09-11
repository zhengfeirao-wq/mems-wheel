"""Physical positions are distinct from the MCU's already-applied CS permutation."""
from .protocol import Frame

# From the original upper-PC mapping; user confirmed this short-cable layout.
SHORT_POSITION_TO_CHANNEL = (
    13, 15, 5, 3, 1, 7, 9, 11, 10, 8, 2, 4, 12, 16, 14, 6,
    26, 24, 32, 30, 19, 21, 25, 23, 17, 28, 27, 18, 20, 22, 29, 31,
)


def physical_values(frame: Frame) -> tuple[tuple[int, ...], tuple[int, ...], int]:
    """Return temperature, pressure, fresh_mask in physical position order."""
    if frame.mapping_revision != 1:
        raise ValueError("unrecognized mapping revision; use wire channel order")
    if frame.channels == 12:
        order = tuple(range(1, 13))
    elif frame.cable == "short":
        order = SHORT_POSITION_TO_CHANNEL
    else:
        raise ValueError("long-cable physical mapping has not been confirmed")
    return (tuple(frame.temperature[i - 1] for i in order),
            tuple(frame.pressure[i - 1] for i in order),
            sum(((frame.fresh_mask >> (i - 1)) & 1) << p for p, i in enumerate(order)))
