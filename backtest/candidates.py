"""Candidate registry validation. Registry metadata never contains behavior."""
import hashlib, json
from pathlib import Path
from backtest.strategy import fingerprint, load_strategy

ROOT=Path(__file__).resolve().parents[1]
ALLOWED_FIELDS={"strategy_id","version","family","status"}

def registry_checksum(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def load_registry(path=ROOT/"strategies/candidates.json", strategies_root=None):
    path=Path(path); strategies_root=Path(strategies_root or ROOT/"strategies"); entries=json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(entries,list): raise ValueError("candidate registry must be a list")
    seen=set(); resolved=[]
    for entry in entries:
        if set(entry) != ALLOWED_FIELDS: raise ValueError("registry may contain candidate metadata only")
        if entry["status"] != "candidate": raise ValueError("registry status must be candidate")
        identity=(entry["strategy_id"],entry["version"])
        if identity in seen: raise ValueError("duplicate candidate strategy_id/version")
        seen.add(identity)
        strategy_path=strategies_root/entry["strategy_id"]/("v"+entry["version"])/"strategy.yaml"
        if not strategy_path.is_file(): raise ValueError("registry references nonexistent strategy version")
        strategy=load_strategy(strategy_path)
        if (strategy["strategy_id"],strategy["strategy_version"],strategy["status"]) != (entry["strategy_id"],entry["version"],entry["status"]): raise ValueError("registry identity does not match canonical strategy")
        resolved.append({**entry,"strategy_path":strategy_path,"fingerprint":fingerprint(strategy)})
    return resolved
