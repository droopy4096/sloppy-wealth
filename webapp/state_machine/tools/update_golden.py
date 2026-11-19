"""Golden results of the engine: regenerate ``tests/golden/golden.json``.

    webapp/.venv/bin/python webapp/state_machine/tools/update_golden.py [--check] [--add FILE ...]
    webapp/.venv/bin/python webapp/state_machine/tools/update_golden.py --values
    (or, from webapp/:  .venv/bin/python -m state_machine.tools.update_golden ...)

``tests/golden/scenarios.json`` holds every golden scenario ({key: scenario}): the samples
(``samples/<file>``), the hand-written fixtures (``fixtures/<file>``) and the scenarios
the reference test suite passed to the engine (``tests/<Test.test>_<hash>``), all synthetic
test data. ``golden.json`` holds, per key, either the validation / run error (type and
message) or the SHA-256 of ``repr()`` of each of ``rows``, ``holdings``, ``ledger`` and
``tax`` of ``run_detailed`` (the ``events`` log is not part of the golden result), plus the
row count and the last row's netWorth in clear. The hashes were frozen from iteration 1
(engine.py on branch poc/python-flask, tag poc-iteration-1) when both engines gave
byte-identical results; ``tests/test_golden.py`` replays them on the current engine.

Run this ONLY after an intended behaviour change, and review first what changed:
``--check`` lists every key whose result differs from golden.json (without writing),
then run without ``--check`` to rewrite the hashes from the CURRENT engine and commit
golden.json together with the change, saying why in the message.
``--add FILE`` adds scenario files to scenarios.json (key ``fixtures/<file name>``) --
synthetic data only, never personal scenarios.

Golden sets per jurisdiction (ADR-0071): the files above are Canada's (frozen from
iteration 1); another jurisdiction has its own ``tests/golden/<code>/scenarios.json`` and
``golden.json`` (e.g. ``tests/golden/us/``), and its package's ``sample.json`` is one of
its scenarios. Without ``--jurisdiction`` every set is checked or rewritten; ``--add``
goes to the set of ``--jurisdiction`` (default CA).

``--values`` regenerates ``tests/golden/values.json`` instead: the golden values of the WP
unit tests (``support.assert_golden``: intermediate results once compared with iteration 1),
by running the state_machine test suite with GOLDEN_UPDATE=1. Review the failing tests of
a normal run first; ``git diff`` shows which keys changed.
"""
import argparse
import copy
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
PACKAGE = TOOLS.parent                      # webapp/state_machine
POC = PACKAGE.parent                        # webapp
GOLDEN = PACKAGE / "tests" / "golden"
SCENARIOS = GOLDEN / "scenarios.json"
RESULTS = GOLDEN / "golden.json"
SECTIONS = ("rows", "holdings", "ledger", "tax")


def digest(value):
    return hashlib.sha256(repr(value).encode()).hexdigest()


def fingerprint(engine, scenario):
    """The golden entry of ``scenario`` on ``engine`` (a module with ``validate`` and
    ``run_detailed``); the scenario is deep-copied."""
    for stage, fn in (("validate", engine.validate), ("run", engine.run_detailed)):
        try:
            out = fn(copy.deepcopy(scenario))
        except Exception as e:  # noqa: BLE001 - the error is the result
            return {"error": {"stage": stage, "type": type(e).__name__, "message": str(e)}}
    rows = out["rows"]
    entry = {"rowCount": len(rows),
             "lastNetWorth": str(rows[-1].get("netWorth")) if rows else None}
    entry.update({section: digest(out[section]) for section in SECTIONS})
    return entry


def mismatch(key, expected, actual):
    """A readable description of every difference (each field that differs, so a change
    confined to rows is told apart from one that also moves the ledger), or None."""
    if expected == actual:
        return None
    fields = [f for f in ("error", "rowCount", "lastNetWorth") + SECTIONS
              if expected.get(f) != actual.get(f)]
    if not fields:
        return f"{key}: differs\n  golden:  {expected!r}\n  current: {actual!r}"
    lines = [f"{key}: {', '.join(fields)} differ"]
    for f in fields:
        if f not in SECTIONS:                   # hashes say nothing; show readable values
            lines.append(f"  {f}: golden {expected.get(f)!r}, current {actual.get(f)!r}")
    return "\n".join(lines)


def golden_dir(code="CA"):
    """The golden folder of a jurisdiction: Canada's is GOLDEN itself."""
    return GOLDEN if code.upper() == "CA" else GOLDEN / code.lower()


def golden_sets():
    """Every jurisdiction with a golden set: CA, then each tests/golden/<code>/."""
    return ["CA"] + sorted(d.name.upper() for d in GOLDEN.iterdir()
                           if d.is_dir() and (d / "scenarios.json").exists())


def load_scenarios(code="CA"):
    return json.loads((golden_dir(code) / "scenarios.json").read_text())


def load_golden(code="CA"):
    path = golden_dir(code) / "golden.json"
    return json.loads(path.read_text()) if path.exists() else {}


def scenario_key(path):
    """``fixtures/<name>``, or the path inside the package (``jurisdictions/us/sample.json``)."""
    path = path.resolve()
    try:
        inside = path.relative_to(PACKAGE)
    except ValueError:
        return f"fixtures/{path.name}"
    return str(inside) if inside.parts[0] != "fixtures" else f"fixtures/{path.name}"


def save(path, data, indent=None):
    text = json.dumps(data, indent=indent, sort_keys=True, separators=(",", ":") if indent is None else None)
    path.write_text(text + "\n")


def compute(engine, scenarios):
    return {key: fingerprint(engine, s) for key, s in scenarios.items()}


def load_engine():
    if str(POC) not in sys.path:
        sys.path.insert(0, str(POC))
    from state_machine import engine
    return engine


def update_values():
    """Rewrite tests/golden/values.json from the current engine (whole suite, stale keys
    dropped)."""
    values = GOLDEN / "values.json"
    values.unlink(missing_ok=True)
    done = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s",
                           "state_machine/tests", "-t", "."], cwd=POC,
                          env=dict(os.environ, GOLDEN_UPDATE="1"))
    print(f"written: {values} ({len(json.loads(values.read_text()))} values)")
    if done.returncode:
        # A failure that is not a golden value (an ordinary assertion or an error) stays
        # failing after an update: say so, the output above lists it.
        print("WARNING: some tests failed while recording (see above); values were written "
              "for the rest. Fix those failures, then run the suite again.")
    return done.returncode


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--check", action="store_true", help="only list differences, do not write")
    ap.add_argument("--add", nargs="+", type=Path, default=[], metavar="FILE",
                    help="add synthetic scenario files to scenarios.json")
    ap.add_argument("--values", action="store_true",
                    help="regenerate the WP tests' golden values (values.json) instead")
    ap.add_argument("--jurisdiction", metavar="CODE",
                    help="only this jurisdiction's golden set (ADR-0071); --add goes there")
    args = ap.parse_args(argv)
    if args.values:
        return update_values()

    codes = [args.jurisdiction.upper()] if args.jurisdiction else golden_sets()
    if args.add and len(codes) > 1:
        codes = ["CA"]
    engine = load_engine()
    failed = False
    for code in codes:
        folder = golden_dir(code)
        scenarios = load_scenarios(code) if (folder / "scenarios.json").exists() else {}
        for f in args.add:
            scenarios[scenario_key(f)] = json.loads(f.read_text())
        if args.add and not args.check:
            folder.mkdir(exist_ok=True)
            save(folder / "scenarios.json", scenarios, indent=None)
        current = compute(engine, scenarios)
        old = load_golden(code)
        changed = [k for k in current if old.get(k) != current[k]]
        for k in changed:
            print(mismatch(k, old.get(k, {}), current[k]) if k in old else f"{k}: new")
        for k in sorted(set(old) - set(current)):
            print(f"{k}: removed")
        label = "" if codes == ["CA"] and not args.jurisdiction else f"{code}: "
        print(f"{label}{len(current)} scenarios, {len(changed)} changed/new, "
              f"{len(set(old) - set(current))} removed")
        if not args.check:
            save(folder / "golden.json", current, indent=1)
            print(f"written: {folder / 'golden.json'}")
        failed |= bool(changed or set(old) - set(current))
    return 1 if args.check and failed else 0


if __name__ == "__main__":
    sys.exit(main())
