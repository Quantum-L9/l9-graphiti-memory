#!/usr/bin/env bash
# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: hooks/graphiti-mark-ok.sh
#   layer: hook
#   owner: memory-control-plane
#   status: active
#   version: 2.2.0
#   updated: 2026-07-22

# Compatibility helper: verify only the currently hydrated task receipt.
set -u
SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
# shellcheck source=graphiti_common.sh
. "$SCRIPT_DIR/graphiti_common.sh"
STATE="$(l9_memory_state_file)"
KEY="${1:-}"
[ -f "$STATE" ] || { printf '%s\n' 'L9 memory evidence is missing; run hydration first' >&2; exit 1; }
python3 - "$STATE" "$KEY" <<'PYCODE'
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

path = Path(sys.argv[1])
requested = sys.argv[2]
data = json.loads(path.read_text(encoding="utf-8"))
current = str(data.get("task_signature") or "")
if not current or (requested and requested != current):
    raise SystemExit("task signature does not match the current hydration receipt")
raw = data.get("hydrated_at")
if not raw or not data.get("hydration_digest") or data.get("hydration_status") not in {"complete", "partial"}:
    raise SystemExit("current hydration receipt is incomplete")
then = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
if then.tzinfo is None:
    then = then.replace(tzinfo=timezone.utc)
ttl = int(data.get("ttl_minutes", 30))
age = (datetime.now(timezone.utc) - then.astimezone(timezone.utc)).total_seconds() / 60
if age < 0 or age > ttl:
    raise SystemExit("current hydration receipt is stale")
values = [str(value) for value in data.get("verified_task_signatures", []) if isinstance(value, str)]
if current not in values:
    values.append(current)
data["verified_task_signatures"] = values
temporary = path.with_name(f".{path.name}.{os.getpid()}.{uuid4().hex}.tmp")
try:
    temporary.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, path)
finally:
    temporary.unlink(missing_ok=True)
PYCODE
