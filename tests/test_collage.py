import unittest

from minifreak_patch.collage import (
    CollageError,
    CollageFrame,
    CollageStreamDecoder,
    FRAME_FLOW,
    FRAME_REQUEST,
)
from minifreak_patch.minifreak_usb import _session_parameter_frame


class CollageFrameTests(unittest.TestCase):
    def test_request_frame(self):
        raw = bytes.fromhex("1103000000080138")
        frame = CollageFrame.from_bytes(raw, direction="bulk-out")
        self.assertEqual(frame.frame_type, FRAME_REQUEST)
        self.assertEqual(frame.declared_length, 3)
        self.assertEqual(frame.channel, 0)
        self.assertEqual(frame.payload, bytes.fromhex("080138"))

    def test_reassembles_usb_packets(self):
        raw = bytes.fromhex("1103000000080138")
        decoder = CollageStreamDecoder()
        self.assertEqual(decoder.feed("bulk-out", raw[:6]), [])
        frames = decoder.feed("bulk-out", raw[6:])
        self.assertEqual(len(frames), 1)
        self.assertEqual(frames[0].raw, raw)

    def test_reassembles_adjacent_flow_frames(self):
        raw = bytes.fromhex("12000000801200000040")
        frames = CollageStreamDecoder().feed("bulk-in", raw)
        self.assertEqual([frame.frame_type for frame in frames], [FRAME_FLOW] * 2)

    def test_rejects_unknown_frame_type(self):
        with self.assertRaises(CollageError):
            CollageFrame.from_bytes(bytes.fromhex("9900000000"))

    def test_encodes_verified_live_session_parameter(self):
        raw = _session_parameter_frame(0x19, 0x3D70)
        self.assertEqual(
            raw.hex(), "130c000000000003011019100000703d38"
        )

    def test_encodes_multi_byte_session_parameter_id(self):
        raw = _session_parameter_frame(218, 0x3D70)
        self.assertEqual(
            raw.hex(), "130d0000000000030110da01100000703d38"
        )


if __name__ == "__main__":
    unittest.main()
