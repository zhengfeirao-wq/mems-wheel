"""Tactile500 V2: native tactile acquisition over PyUSB."""
__version__ = "0.4.0"

from .api import ReceivedFrame, Snapshot, TactileHand, TactileSystem
from .protocol import Frame, StreamDecoder, decode_frame
from .recording import Recorder, read_recording
from .tare import (SATURATION, SENTINEL, ChannelBaseline, TareFilter,
                   TareJournal, TareResult, measure_baseline, restore)

__all__ = ["TactileSystem", "TactileHand", "ReceivedFrame", "Snapshot", "Frame",
           "StreamDecoder", "decode_frame", "Recorder", "read_recording",
           "measure_baseline", "TareFilter", "TareJournal", "TareResult",
           "ChannelBaseline", "restore", "SATURATION", "SENTINEL"]

