"""Deterministic source identity, UTC semantics and raw evidence."""
import hashlib
import json
from datetime import datetime,timezone
from pathlib import Path

def canonical(value):
    return json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(",",":"))

def digest(value):
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()

def utc(value):
    dt=datetime.fromisoformat(value.replace("Z","+00:00"))
    if dt.tzinfo is None: raise ValueError("timezone_required")
    return dt.astimezone(timezone.utc)

def read(path):
    value=json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value,dict): raise ValueError("object_required")
    return value

