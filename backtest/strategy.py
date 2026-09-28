"""Canonical immutable strategy-version loading and behavior fingerprints."""
import hashlib, json, re
from pathlib import Path
import yaml
from backtest.validation import validate_strategy

SEMVER = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")
BEHAVIOR_KEYS = ("strategy_id", "universe", "timeframe", "entry", "exit", "risk", "pyramiding", "position_sizing", "session", "execution")

def behavior_projection(strategy):
    return {key: strategy[key] for key in BEHAVIOR_KEYS if key in strategy}

def fingerprint(strategy):
    payload=json.dumps(behavior_projection(strategy),sort_keys=True,separators=(",",":"))
    return hashlib.sha256(payload.encode()).hexdigest()

def load_strategy(path):
    path=Path(path); strategy=yaml.safe_load(path.read_text(encoding="utf-8"))
    if not SEMVER.fullmatch(strategy.get("strategy_version", "")): raise ValueError("strategy_version must be MAJOR.MINOR.PATCH")
    if path.name != "strategy.yaml" or path.parent.name != "v" + strategy["strategy_version"]: raise ValueError("strategy directory version must match strategy.yaml")
    validate_strategy(strategy)
    return strategy

def version_directory(family_directory, version):
    """Return a new-version destination, refusing silent historical overwrite."""
    if not SEMVER.fullmatch(version):
        raise ValueError("strategy_version must be MAJOR.MINOR.PATCH")
    target=Path(family_directory) / ("v" + version)
    if target.exists():
        raise FileExistsError("strategy version already exists and is immutable")
    return target

def compare(left, right):
    a,b=behavior_projection(left),behavior_projection(right); changed=[]
    def walk(x,y,p=""):
        for key in sorted(set(x)|set(y)):
            q=f"{p}.{key}" if p else key
            if isinstance(x.get(key),dict) and isinstance(y.get(key),dict): walk(x[key],y[key],q)
            elif x.get(key)!=y.get(key): changed.append({"field":q,"left":x.get(key),"right":y.get(key)})
    walk(a,b); return changed
