#!/usr/bin/env python3
"""Validate synthetic device telemetry before using it for operational decisions."""

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

FIELDS = ("event_id", "device_id", "site_id", "brand", "observed_at", "received_at", "status")
SKEW_SECONDS = 5


def timestamp(value):
    if not isinstance(value, str):
        raise ValueError("timestamp must be a string")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("invalid ISO timestamp") from exc
    if parsed.tzinfo is None:
        raise ValueError("timestamp requires a timezone")
    return parsed.astimezone(timezone.utc)


def utc(value):
    return value.isoformat().replace("+00:00", "Z")


def read_inventory(path):
    data = json.loads(Path(path).read_text())
    if not isinstance(data, list) or not data:
        raise ValueError("inventory must be a nonempty array")
    inventory = {}
    for item in data:
        if not isinstance(item, dict):
            raise ValueError("inventory entries must be objects")
        for field in ("device_id", "site_id", "brand"):
            if not isinstance(item.get(field), str) or not item[field].strip():
                raise ValueError("inventory requires nonempty device_id, site_id and brand")
        budget = item.get("freshness_seconds")
        if type(budget) is not int or budget <= 0:
            raise ValueError("freshness_seconds must be a positive integer")
        if item["device_id"] in inventory:
            raise ValueError("duplicate device_id in inventory")
        inventory[item["device_id"]] = item
    return inventory


def validate_event(raw, inventory, now):
    if not isinstance(raw, dict):
        raise ValueError("event must be an object")
    if any(not isinstance(raw.get(f), str) or not raw[f].strip() for f in FIELDS):
        raise ValueError("missing or invalid required string field")
    event = {field: raw[field] for field in FIELDS}
    if event["status"] not in ("ok", "error"):
        raise ValueError("status must be ok or error")
    expected = inventory.get(event["device_id"])
    if expected is None:
        raise ValueError("device absent from inventory")
    if any(event[field] != expected[field] for field in ("site_id", "brand")):
        raise ValueError("device attribution disagrees with inventory")
    observed, received = timestamp(event["observed_at"]), timestamp(event["received_at"])
    if (observed - received).total_seconds() > SKEW_SECONDS:
        raise ValueError("observation is after receipt beyond clock tolerance")
    if max((observed - now).total_seconds(), (received - now).total_seconds()) > SKEW_SECONDS:
        raise ValueError("timestamp is in the future beyond clock tolerance")
    event["observed_at"], event["received_at"] = utc(observed), utc(received)
    return event


def evaluate(inventory, lines, now, delivery_budget=60):
    counts = Counter(records_read=0, invalid_records=0, duplicate_replays=0,
                     conflicting_records=0, accepted_events=0)
    grouped, by_device = defaultdict(list), defaultdict(list)
    issues = []
    for line_no, line in enumerate(lines, 1):
        if not line.strip():
            continue
        counts["records_read"] += 1
        try:
            event = validate_event(json.loads(line), inventory, now)
        except (ValueError, TypeError) as exc:
            counts["invalid_records"] += 1
            issues.append({"line": line_no, "reason": str(exc)})
            continue
        grouped[event["event_id"]].append((line_no, event))

    for event_id, records in sorted(grouped.items()):
        fingerprints = {json.dumps(event, sort_keys=True) for _, event in records}
        if len(fingerprints) > 1:
            counts["conflicting_records"] += len(records)
            issues.append({"event_id": event_id, "reason": "conflicting ID quarantined",
                           "lines": [line for line, _ in records]})
            continue
        counts["duplicate_replays"] += len(records) - 1
        counts["accepted_events"] += 1
        event = records[0][1]
        by_device[event["device_id"]].append(event)

    devices = []
    for device_id, expected in sorted(inventory.items()):
        result = {"device_id": device_id, "brand": expected["brand"], "site_id": expected["site_id"],
                  "state": "unknown", "reason": "missing", "event_age_seconds": None,
                  "delivery_seconds": None, "delivery_over_budget": False}
        events = by_device[device_id]
        if events:
            latest_time = max(timestamp(event["observed_at"]) for event in events)
            latest = [event for event in events if timestamp(event["observed_at"]) == latest_time]
            selected = max(latest, key=lambda event: (timestamp(event["received_at"]), event["event_id"]))
            age = max(0, (now - latest_time).total_seconds())
            delay = max(0, (timestamp(selected["received_at"]) - latest_time).total_seconds())
            result.update(event_age_seconds=age, delivery_seconds=delay,
                          delivery_over_budget=delay > delivery_budget)
            if len({event["status"] for event in latest}) > 1:
                result["reason"] = "conflicting latest observations"
            elif age > expected["freshness_seconds"]:
                result["reason"] = "stale"
            elif selected["status"] == "error":
                result.update(state="degraded", reason="fresh explicit error")
            else:
                result.update(state="healthy", reason="fresh ok observation")
        devices.append(result)

    states = {state: sum(device["state"] == state for device in devices)
              for state in ("healthy", "degraded", "unknown")}
    fleet = "degraded" if states["degraded"] else "unknown" if states["unknown"] else "healthy"
    late = sum(device["delivery_over_budget"] for device in devices)
    passed = fleet == "healthy" and counts["invalid_records"] == 0 and counts["conflicting_records"] == 0 and late == 0
    return {"as_of": utc(now), "delivery_budget_seconds": delivery_budget,
            "clock_tolerance_seconds": SKEW_SECONDS, "quality_gate": "pass" if passed else "fail",
            "fleet_state": fleet, "inventory_devices": len(inventory), "counts": dict(counts),
            "states": states, "latest_delivery_over_budget": late,
            "devices": devices, "issues": issues}


def print_report(report):
    print("Telemetry quality gate | " + report["as_of"])
    print("Gate: " + report["quality_gate"].upper() + " | Fleet: " + report["fleet_state"])
    print("Inventory: {inventory_devices} | Latest delivery over budget: {latest_delivery_over_budget}".format(**report))
    print("Records: " + ", ".join(f"{key}={value}" for key, value in report["counts"].items()))
    print("States: " + ", ".join(f"{key}={value}" for key, value in report["states"].items()))
    print("device_id | state | reason | event age (s) | delivery (s)")
    for device in report["devices"]:
        age = "-" if device["event_age_seconds"] is None else f"{device['event_age_seconds']:g}"
        delay = "-" if device["delivery_seconds"] is None else f"{device['delivery_seconds']:g}"
        print(f"{device['device_id']} | {device['state']} | {device['reason']} | {age} | {delay}")
    for issue in report["issues"]:
        print("Issue: " + json.dumps(issue, sort_keys=True))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inventory", required=True)
    parser.add_argument("--events", required=True)
    parser.add_argument("--now", required=True, help="Timezone-aware fixed evaluation timestamp")
    parser.add_argument("--delivery-budget", type=int, default=60)
    parser.add_argument("--json-out", help="Optional report file, replaced if it exists")
    args = parser.parse_args()
    try:
        if args.delivery_budget <= 0:
            raise ValueError("delivery budget must be positive")
        inventory = read_inventory(args.inventory)
        with Path(args.events).open() as lines:
            report = evaluate(inventory, lines, timestamp(args.now), args.delivery_budget)
        if args.json_out:
            Path(args.json_out).write_text(json.dumps(report, indent=2) + "\n")
        print_report(report)
        return 0 if report["quality_gate"] == "pass" else 1
    except (OSError, ValueError, TypeError) as exc:
        print("Input/configuration error: " + str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
