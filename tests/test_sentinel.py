import base64
import copy
import json
import tempfile
import unittest
from pathlib import Path

from minifreak_patch.minifreak_usb import _session_parameter_frame
from minifreak_patch.collage import RetrievedResource
from minifreak_patch.preset import MiniFreakPreset
from minifreak_patch.sentinel import (
    SENTINEL_SCHEMA,
    analyze_sentinel_experiment,
    analyze_named_preset_corpus,
    collect_named_preset_corpus,
    decode_session_delta,
    generate_sentinel_experiment,
)


class SentinelTests(unittest.TestCase):
    def test_generate_creates_distinct_roundtrippable_mnfx_shots(self):
        base = Path(__file__).parents[1] / "presets" / "minifreak-default-base.mnfx"
        with tempfile.TemporaryDirectory() as temp:
            manifest_path = generate_sentinel_experiment(
                base,
                temp,
                parameters=("Vcf_Cutoff", "Vcf_Resonance"),
            )
            manifest = json.loads(manifest_path.read_text())
            shot_a = MiniFreakPreset.from_file(Path(temp) / "sentinel-a.mnfx")
            shot_b = MiniFreakPreset.from_file(Path(temp) / "sentinel-b.mnfx")
        self.assertEqual(manifest["schema_version"], SENTINEL_SCHEMA)
        self.assertNotEqual(shot_a.params["Vcf_Cutoff"], shot_b.params["Vcf_Cutoff"])
        self.assertNotEqual(
            shot_a.params["Vcf_Resonance"], shot_b.params["Vcf_Resonance"]
        )

    def test_decode_session_delta(self):
        frame = _session_parameter_frame(0x2A, 5000)
        self.assertEqual(decode_session_delta(frame[5:]), (0x2A, 5000))

    def test_analyzer_finds_unique_offset_and_session_id(self):
        baseline = bytes(3328)
        shot_a = bytearray(baseline)
        shot_b = bytearray(baseline)
        shot_a[220:222] = (5000).to_bytes(2, "little", signed=True)
        shot_b[220:222] = (12000).to_bytes(2, "little", signed=True)
        manifest = {
            "schema_version": SENTINEL_SCHEMA,
            "family": "fixture",
            "parameters": [
                {
                    "name": "Fixture_Value",
                    "codes": [
                        {"raw_s16": 5000, "value": 5000 / 32767},
                        {"raw_s16": 12000, "value": 12000 / 32767},
                    ],
                }
            ],
        }

        def document(payload):
            return {
                "minifreak": {
                    "hardware": {
                        "raw_payload_base64": base64.b64encode(payload).decode()
                    }
                }
            }

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "manifest.json").write_text(json.dumps(manifest))
            (root / "baseline.json").write_text(json.dumps(document(baseline)))
            (root / "a.json").write_text(json.dumps(document(bytes(shot_a))))
            (root / "b.json").write_text(json.dumps(document(bytes(shot_b))))
            (root / "a.log").write_text(
                "1 kind=bulk-out data=" + _session_parameter_frame(0x2A, 5000).hex() + "\n"
            )
            (root / "b.log").write_text(
                "2 kind=bulk-out data=" + _session_parameter_frame(0x2A, 12000).hex() + "\n"
            )
            result = analyze_sentinel_experiment(
                root / "manifest.json",
                root / "baseline.json",
                root / "a.json",
                root / "b.json",
                capture_a=root / "a.log",
                capture_b=root / "b.log",
            )
        mapping = result["results"][0]
        self.assertEqual(mapping["buffer_offset_candidates"], [220])
        self.assertEqual(mapping["session_parameter_id_candidates"], [0x2A])
        self.assertEqual(mapping["status"], "unique")

    def test_natural_corpus_maps_named_parameter_across_presets(self):
        base_path = (
            Path(__file__).parents[1] / "presets" / "minifreak-default-base.mnfx"
        )
        base = MiniFreakPreset.from_file(base_path)
        values = (0.1, 0.3, 0.6, 0.9)

        class FakeTransport:
            def __init__(self, payloads):
                self.payloads = payloads

            def read_preset_metadata(self, slot):
                data = bytearray(128)
                name = f"Corpus {slot}".encode()
                data[8 : 8 + len(name)] = name
                return RetrievedResource(1, b"", "metadata", bytes(data), 128, True)

            def read_saved_preset(self, slot):
                data = self.payloads[slot - 1]
                return RetrievedResource(1, b"", "preset", data, len(data), True)

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            exports = root / "exports"
            corpus = root / "corpus"
            exports.mkdir()
            payloads = []
            for slot, value in enumerate(values, 1):
                preset = copy.deepcopy(base)
                preset.name = f"Corpus {slot}"
                preset.set_param("Vcf_Cutoff", value)
                preset.write_zip(exports / f"{slot}.mnfx")
                payload = bytearray(3328)
                name = preset.name.encode()
                payload[8 : 8 + len(name)] = name
                payload[200:202] = round(value * 32767).to_bytes(
                    2, "little", signed=True
                )
                payloads.append(bytes(payload))
            manifest = collect_named_preset_corpus(
                FakeTransport(payloads),
                exports,
                corpus,
                scan_slots=4,
                max_matches=4,
            )
            result = analyze_named_preset_corpus(
                manifest, parameters=("Vcf_Cutoff",)
            )
        mapping = result["results"][0]
        self.assertEqual(mapping["status"], "unique")
        self.assertEqual(mapping["candidates"][0]["offset"], 200)
        self.assertEqual(mapping["candidates"][0]["encoding"], "unit_s16")


if __name__ == "__main__":
    unittest.main()
