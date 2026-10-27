"""Guard against plausible-but-invalid export metadata passing validation."""
import copy
import importlib.util
import unittest
from pathlib import Path

SPEC = importlib.util.spec_from_file_location("validate", Path(__file__).parents[1] / "scripts/validate.py")
validate = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(validate)

VALID = {
    "format": {"duration": "160.000000"},
    "streams": [
        {"codec_type": "video", "codec_name": "h264", "width": 1920, "height": 1080,
         "sample_aspect_ratio": "1:1", "avg_frame_rate": "30/1", "r_frame_rate": "30/1",
         "nb_read_frames": "4800", "duration": "160.000000", "pix_fmt": "yuv420p"},
        {"codec_type": "audio", "codec_name": "aac", "duration": "160.000000",
         "channels": 2, "sample_rate": "48000"},
    ],
}


class MetadataTests(unittest.TestCase):
    def test_valid_master_metadata(self):
        self.assertEqual(validate.metadata_errors(VALID), [])

    def test_one_frame_short_does_not_round_to_pass(self):
        bad = copy.deepcopy(VALID)
        bad["streams"][0]["nb_read_frames"] = "4799"
        self.assertTrue(validate.metadata_errors(bad))

    def test_2997_fps_is_rejected(self):
        bad = copy.deepcopy(VALID)
        bad["streams"][0]["avg_frame_rate"] = "30000/1001"
        self.assertTrue(validate.metadata_errors(bad))

    def test_missing_audio_rejected(self):
        bad = copy.deepcopy(VALID)
        bad["streams"] = bad["streams"][:1]
        self.assertTrue(validate.metadata_errors(bad))

    def test_short_audio_rejected(self):
        bad = copy.deepcopy(VALID)
        bad["streams"][1]["duration"] = "153.0"
        self.assertTrue(validate.metadata_errors(bad))

    def test_nonsquare_pixels_rejected(self):
        bad = copy.deepcopy(VALID)
        bad["streams"][0]["sample_aspect_ratio"] = "4:3"
        self.assertTrue(validate.metadata_errors(bad))

    def test_nan_duration_rejected(self):
        bad = copy.deepcopy(VALID)
        bad["format"]["duration"] = "nan"
        self.assertTrue(validate.metadata_errors(bad))

    def test_bad_fps_does_not_crash(self):
        for rate in ("0/0", "N/A", None):
            bad = copy.deepcopy(VALID)
            bad["streams"][0]["avg_frame_rate"] = rate
            self.assertTrue(validate.metadata_errors(bad))


if __name__ == "__main__":
    unittest.main()
