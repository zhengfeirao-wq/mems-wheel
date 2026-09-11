import binascii
from pathlib import Path

import pytest

from tactile500.protocol import CaptureStats, StreamDecoder, decode_frame
from helpers import packet


def test_six_identities_crc_signed_fields_and_revision():
    for identity in (8, 9, 10, 11, 14, 15):
        raw = packet(identity)
        frame = decode_frame(raw)
        assert frame.raw == raw
        assert frame.version == 0x21
        assert frame.channels == (32 if identity & 2 else 12)
        assert frame.temperature[0] == -frame.channels
        assert frame.pressure[0] == -1600
        assert frame.cable == ("none" if frame.channels == 12 else "short" if identity & 4 else "long")
        damaged = bytearray(raw)
        damaged[20] ^= 1
        with pytest.raises(ValueError, match="CRC"):
            decode_frame(damaged)


def test_independent_c_vectors():
    data = (Path(__file__).parent / "fixtures" / "protocol_vectors.bin").read_bytes()
    result = StreamDecoder().feed(data)
    assert [x.identity for x in result] == [8, 9, 10, 11, 14, 15]
    assert all(binascii.crc_hqx(x.raw[:-2], 0xFFFF) == int.from_bytes(x.raw[-2:], "little") for x in result)


def test_resync_arbitrary_chunks_noise_corruption_and_old_protocol():
    good = packet(14, 2, 4000)
    bad = bytearray(packet())
    bad[-1] ^= 8
    source = b"BT\xff\x00" + bytes(bad) + good + packet(8, 3, 6000)
    for size in (1, 7, 32, 64, 160, 512):
        decoder = StreamDecoder()
        result = []
        for i in range(0, len(source), size):
            result += decoder.feed(source[i:i + size])
        assert [f.sequence for f in result] == [2, 3]
        assert decoder.rejected_candidates >= 1
        assert len(decoder.buffer) == 0


def test_wrap_gap_duplicate_and_reset_do_not_invent_billions_of_losses():
    stats = CaptureStats()
    for seq, ts in ((0xFFFFFFFF, 0xFFFFFC18), (0, 1000), (3, 7000), (3, 7000), (1, 2000)):
        stats.add(decode_frame(packet(sequence=seq, timestamp=ts)))
    assert stats.missing_slots == 2
    assert stats.duplicates == 1
    assert stats.resets_or_reorders == 1
