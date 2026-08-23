#!/usr/bin/env python3
# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: tools/ci/nightly_maintenance_gate.py
#   layer: assurance
#   owner: memory-control-plane
#   status: active
#   version: 2.2.0
#   updated: 2026-07-22

"""Decide whether this scheduled firing is the nightly 02:00 America/New_York run.

GitHub Actions evaluates `schedule:` cron in UTC only, so no single cron
expression is 02:00 in a zone that observes daylight saving time. The workflow
therefore fires at both candidate instants -- 06:00 and 07:00 UTC, which are
02:00 EDT and 02:00 EST -- and this gate lets exactly one of them through.

On the spring-forward date, 02:00 local does not exist at all: the clock jumps
from 01:59 EST to 03:00 EDT. The gate admits the 03:00 firing on that date, so
the run still happens once rather than being silently skipped for a day.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

MAINTENANCE_TIMEZONE = "America/New_York"
MAINTENANCE_HOUR = 2


def local_hour_exists(day: date, hour: int, tz: ZoneInfo) -> bool:
    """False when a daylight-saving jump removes ``hour`` from ``day``."""

    local = datetime(day.year, day.month, day.day, hour, 0, tzinfo=tz)
    round_tripped = local.astimezone(timezone.utc).astimezone(tz)
    return round_tripped.replace(tzinfo=tz) == local


def decide(
    now_utc: datetime,
    *,
    timezone_name: str = MAINTENANCE_TIMEZONE,
    hour: int = MAINTENANCE_HOUR,
) -> tuple[bool, str]:
    """Return whether to run, and why."""

    tz = ZoneInfo(timezone_name)
    local = now_utc.astimezone(tz)
    stamp = local.strftime("%Y-%m-%d %H:%M %Z")

    if local.hour == hour:
        return True, f"local time is {stamp}; this is the {hour:02d}:00 run"
    if local.hour == hour + 1 and not local_hour_exists(local.date(), hour, tz):
        return (
            True,
            (
                f"local time is {stamp}; {hour:02d}:00 does not exist on this "
                "date because of the daylight-saving jump, so this firing is the run"
            ),
        )
    return False, f"local time is {stamp}; not the {hour:02d}:00 run"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--now",
        default=None,
        help="RFC3339 UTC instant to evaluate (defaults to the current time)",
    )
    parser.add_argument("--timezone", default=MAINTENANCE_TIMEZONE)
    parser.add_argument("--hour", type=int, default=MAINTENANCE_HOUR)
    parser.add_argument(
        "--force",
        action="store_true",
        help="bypass the gate (manual dispatch)",
    )
    args = parser.parse_args()

    now_utc = (
        datetime.fromisoformat(args.now).astimezone(timezone.utc)
        if args.now
        else datetime.now(timezone.utc)
    )
    if args.force:
        should_run, reason = True, "gate bypassed by manual dispatch"
    else:
        should_run, reason = decide(now_utc, timezone_name=args.timezone, hour=args.hour)

    sys.stdout.write(
        json.dumps(
            {
                "should_run": should_run,
                "reason": reason,
                "evaluated_at_utc": now_utc.isoformat(),
                "timezone": args.timezone,
            },
            indent=2,
        )
        + "\n"
    )

    output_path = os.environ.get("GITHUB_OUTPUT")
    if output_path:
        with open(output_path, "a", encoding="utf-8") as handle:
            handle.write(f"should_run={'true' if should_run else 'false'}\n")
            handle.write(f"reason={reason}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
