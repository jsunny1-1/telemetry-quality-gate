import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from gate import evaluate, read_inventory, timestamp

ROOT = Path(__file__).parent
NOW = timestamp("2026-01-15T12:00:00Z")
INVENTORY = {"d1": {"device_id": "d1", "site_id": "s1", "brand": "Demo", "freshness_seconds": 300}}


def event(**changes):
    value = dict(event_id="e1", device_id="d1", site_id="s1", brand="Demo",
                 observed_at="2026-01-15T11:59:30Z", received_at="2026-01-15T11:59:31Z", status="ok")
    value.update(changes)
    return value


def run(*events):
    return evaluate(INVENTORY, [json.dumps(item) for item in events], NOW)


class GateTests(unittest.TestCase):
    def test_recent_receipt_does_not_make_old_observation_healthy(self):
        report = run(event(observed_at="2026-01-15T11:00:00Z", received_at="2026-01-15T11:59:59Z"))
        self.assertEqual(report["devices"][0]["reason"], "stale")
        self.assertEqual(report["fleet_state"], "unknown")
        self.assertEqual(report["devices"][0]["delivery_seconds"], 3599)

    def test_missing_data_does_not_claim_device_outage(self):
        report = run()
        self.assertEqual(report["fleet_state"], "unknown")
        self.assertEqual(report["states"]["degraded"], 0)
        self.assertEqual(report["quality_gate"], "fail")

    def test_replay_does_not_inflate_events_or_fail_gate(self):
        report = run(event(), event())
        self.assertEqual(report["counts"]["accepted_events"], 1)
        self.assertEqual(report["counts"]["duplicate_replays"], 1)
        self.assertEqual(report["quality_gate"], "pass")

    def test_conflicting_event_id_is_quarantined_in_either_order(self):
        for records in [(event(), event(status="error")), (event(status="error"), event())]:
            report = run(*records)
            self.assertEqual(report["counts"]["accepted_events"], 0)
            self.assertEqual(report["counts"]["conflicting_records"], 2)
            self.assertEqual(report["fleet_state"], "unknown")

    def test_latest_timestamp_with_conflicting_status_is_unknown(self):
        report = run(event(), event(event_id="e2", status="error"))
        self.assertEqual(report["devices"][0]["reason"], "conflicting latest observations")
        self.assertEqual(report["fleet_state"], "unknown")

    def test_old_error_arriving_late_does_not_override_new_ok(self):
        report = run(event(), event(event_id="old", observed_at="2026-01-15T11:59:00Z",
                                   received_at="2026-01-15T11:59:59Z", status="error"))
        self.assertEqual(report["fleet_state"], "healthy")

    def test_equivalent_timezones_deduplicate(self):
        report = run(event(), event(observed_at="2026-01-15T06:59:30-05:00",
                                   received_at="2026-01-15T06:59:31-05:00"))
        self.assertEqual(report["counts"]["duplicate_replays"], 1)

    def test_invalid_inputs_cannot_make_inventory_healthy(self):
        bad = [event(brand="Wrong"), event(device_id="missing"), event(status="unknown"),
               event(observed_at="2026-01-15T11:59:30"),
               event(observed_at="2026-01-15T12:05:00Z", received_at="2026-01-15T12:05:01Z"),
               event(observed_at="2026-01-15T11:59:40Z", received_at="2026-01-15T11:59:00Z")]
        report = run(*bad)
        self.assertEqual(report["counts"]["invalid_records"], len(bad))
        self.assertEqual(report["fleet_state"], "unknown")

    def test_invalid_record_fails_gate_even_when_devices_are_healthy(self):
        report = evaluate(INVENTORY, [json.dumps(event()), "invalid JSON"], NOW)
        self.assertEqual(report["fleet_state"], "healthy")
        self.assertEqual(report["quality_gate"], "fail")

    def test_fresh_device_can_have_delivery_slo_failure(self):
        report = run(event(observed_at="2026-01-15T11:57:00Z", received_at="2026-01-15T11:59:30Z"))
        self.assertEqual(report["fleet_state"], "healthy")
        self.assertEqual(report["latest_delivery_over_budget"], 1)
        self.assertEqual(report["quality_gate"], "fail")

    def test_fresh_error_is_degraded(self):
        self.assertEqual(run(event(status="error"))["fleet_state"], "degraded")

    def test_inventory_duplicate_is_configuration_error(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "inventory.json"
            path.write_text(json.dumps([INVENTORY["d1"], INVENTORY["d1"]]))
            with self.assertRaisesRegex(ValueError, "duplicate device_id"):
                read_inventory(path)

    def test_cli_exit_codes_and_fixture_accounting(self):
        with tempfile.TemporaryDirectory() as directory:
            inventory, events = Path(directory) / "inventory.json", Path(directory) / "events.jsonl"
            inventory.write_text(json.dumps(list(INVENTORY.values())))
            events.write_text(json.dumps(event()) + "\n")
            command = [sys.executable, str(ROOT / "gate.py"), "--inventory", str(inventory),
                       "--events", str(events), "--now", "2026-01-15T12:00:00Z"]
            self.assertEqual(subprocess.run(command, capture_output=True).returncode, 0)
            events.write_text("")
            self.assertEqual(subprocess.run(command, capture_output=True).returncode, 1)
            inventory.write_text("[]")
            self.assertEqual(subprocess.run(command, capture_output=True).returncode, 2)
        demo = evaluate(read_inventory(ROOT / "fixtures/inventory.json"),
                        (ROOT / "fixtures/events.jsonl").read_text().splitlines(), NOW)
        counts = demo["counts"]
        self.assertEqual(counts["records_read"], sum(counts[key] for key in
                         ("invalid_records", "duplicate_replays", "conflicting_records", "accepted_events")))
        self.assertEqual(demo["states"], {"healthy": 2, "degraded": 1, "unknown": 3})


if __name__ == "__main__":
    unittest.main()
