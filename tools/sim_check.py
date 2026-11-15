"""Before a test request: check the CPU simulation matches the patch and still reproduces the last measured run
(DIRECTOR-WORK 2.3.0, N3).

A fix was tuned in a CPU simulation, but the patch used other timing points and another constant than the simulation;
the test run then measured something the simulation never predicted, and a GPU / device window was spent finding that
out. The rule: the patch's timing points, constants and target algorithm live in one named config file (JSON) that both
the patch and the simulation read. This tool compares them and asks the simulation to reproduce the last measured run.

  sim_check.py --patch-config PATCH.json --sim-config SIM.json [--measured LAST.json --sim-output OUT.json]
               [--tol 0.05] [--abs-tol 0] [--key-tol NAME=VALUE ...] [--keys NAME ...]

  params     every named parameter of the patch config must be in the simulation config with the same value: numbers
             equal (within --abs-tol when given), text and booleans exactly. Nested objects are compared by dotted
             name (`timing.release_frame`). A parameter only one side has is a mismatch. When both paths are the
             same file it says so (the intended setup) and the comparison passes by construction.
             --keys limits the comparison to these names (default: every name in the patch config).
  reproduce  with --measured (numbers recorded from the last real run) and --sim-output (the simulation's numbers for
             the same input): every measured number must be within tolerance of the simulation's: relative --tol
             (default 0.05 = 5 %), or --key-tol NAME=VALUE for one name (relative), or absolute when --abs-tol is
             given and larger. A measured name the simulation does not output is a mismatch. Without --measured
             the check fails (REPRODUCE: MISSING) unless --first-run says no run has been measured yet.

Prints one line per name (OK / MISMATCH / OFF) and a last line
`SIM_CHECK: PASS|FAIL params=n mismatched=n measured=n off=n`. Any mismatch fails with "fix the simulation first":
the test request waits until the simulation and the patch agree and the simulation reproduces the last run.
Exit 0 PASS, 1 FAIL, 2 cannot read the input. Only reads. Not a per-turn read: run it before writing a TEST REQUEST.
"""
import argparse
import json
import math
import pathlib
import sys


def flat(data, prefix=""):
    """{dotted name: value} of a JSON object; lists are values."""
    out = {}
    for key, value in data.items():
        name = f"{prefix}{key}"
        if isinstance(value, dict):
            out.update(flat(value, name + "."))
        else:
            out[name] = value
    return out


def load(path, what):
    data = json.loads(pathlib.Path(path).read_text(encoding="utf-8-sig"))
    if not isinstance(data, dict):
        raise ValueError(f"{what} {path} is not a JSON object")
    return flat(data)


def number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def same(a, b, abs_tol):
    if number(a) and number(b):
        return math.isclose(a, b, rel_tol=0.0, abs_tol=abs_tol) if abs_tol else a == b
    return type(a) is type(b) and a == b


def compare_params(patch, sim, keys, abs_tol):
    lines, bad = [], 0
    for name in keys or sorted(patch):
        if name not in patch:
            lines.append(f"MISMATCH {name}: not in the patch config")
            bad += 1
        elif name not in sim:
            lines.append(f"MISMATCH {name}: patch {patch[name]!r}, not in the simulation config")
            bad += 1
        elif not same(patch[name], sim[name], abs_tol):
            lines.append(f"MISMATCH {name}: patch {patch[name]!r}, simulation {sim[name]!r}")
            bad += 1
        else:
            lines.append(f"OK       {name} = {patch[name]!r}")
    if not keys:
        for name in sorted(set(sim) - set(patch)):
            lines.append(f"~ simulation only {name} = {sim[name]!r} (not a patch parameter; not compared)")
    return lines, bad


def compare_run(measured, output, tol, key_tol, abs_tol):
    lines, off = [], 0
    for name in sorted(measured):
        want = measured[name]
        if not number(want):
            continue
        got = output.get(name)
        if not number(got):
            lines.append(f"OFF      {name}: measured {want!r}, the simulation gives {'nothing' if got is None else repr(got)}")
            off += 1
            continue
        rel = key_tol.get(name, tol)
        if math.isclose(got, want, rel_tol=rel, abs_tol=abs_tol):
            lines.append(f"OK       {name}: measured {want!r}, simulated {got!r}")
        else:
            gap = abs(got - want) / abs(want) * 100 if want else float("inf")
            lines.append(f"OFF      {name}: measured {want!r}, simulated {got!r} ({gap:.1f} % > {rel * 100:g} %)")
            off += 1
    return lines, off


def key_tolerances(items):
    out = {}
    for item in items:
        name, sep, value = item.partition("=")
        if not sep or not name.strip():
            raise ValueError(f"--key-tol takes NAME=VALUE, got {item!r}")
        out[name.strip()] = float(value)
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--patch-config", required=True, metavar="JSON", help="the named config the patch reads")
    ap.add_argument("--sim-config", required=True, metavar="JSON", help="the config the simulation reads")
    ap.add_argument("--keys", nargs="+", default=[], metavar="NAME", help="compare only these parameter names")
    ap.add_argument("--measured", metavar="JSON", help="numbers measured in the last real run")
    ap.add_argument("--sim-output", metavar="JSON", help="the simulation's numbers for the same input")
    ap.add_argument("--first-run", action="store_true", help="no measured run exists yet: skip the reproduction")
    ap.add_argument("--tol", type=float, default=0.05, help="relative tolerance for --measured (default 0.05)")
    ap.add_argument("--key-tol", action="append", default=[], metavar="NAME=VALUE", help="relative tolerance for one name")
    ap.add_argument("--abs-tol", type=float, default=0.0, help="absolute tolerance (params and measured numbers)")
    a = ap.parse_args(argv)
    sys.stdout.reconfigure(encoding="utf-8")
    if bool(a.measured) != bool(a.sim_output):
        ap.error("--measured and --sim-output go together")
    try:
        key_tol = key_tolerances(a.key_tol)
        patch, sim = load(a.patch_config, "--patch-config"), load(a.sim_config, "--sim-config")
        measured = load(a.measured, "--measured") if a.measured else {}
        output = load(a.sim_output, "--sim-output") if a.sim_output else {}
    except (OSError, ValueError) as error:
        print(f"SIM_CHECK: NOT_RUN {type(error).__name__}: {str(error)[:200]}")
        return 2
    one_file = pathlib.Path(a.patch_config).resolve() == pathlib.Path(a.sim_config).resolve()
    print("PARAMS: " + ("the patch and the simulation read the same file (intended)" if one_file
                        else "two config files; every patch parameter is compared"))
    lines, bad = compare_params(patch, sim, a.keys, a.abs_tol)
    for line in lines:
        print(f"  {line}")
    off, count = 0, 0
    if a.measured:
        count = sum(number(v) for v in measured.values())
        print(f"REPRODUCE: the simulation against the last measured run ({count} number(s))")
        run_lines, off = compare_run(measured, output, a.tol, key_tol, a.abs_tol)
        for line in run_lines:
            print(f"  {line}")
        if not count:
            print("  ~ the measured file holds no numbers: nothing was reproduced")
    elif a.first_run:
        print("REPRODUCE: SKIP --first-run (no measured run yet; the next test request needs --measured)")
    else:
        print("REPRODUCE: MISSING (give --measured and --sim-output: the simulation must reproduce the last run; "
              "--first-run when there has been none)")
        off = 1
    failed = bad or off
    if failed:
        print("fix the simulation first: the test request waits until the patch and the simulation agree"
              + (" and the simulation reproduces the last measured run" if a.measured else ""))
    print(f"SIM_CHECK: {'FAIL' if failed else 'PASS'} params={len(lines) - sum(l.startswith('~') for l in lines)} "
          f"mismatched={bad} measured={count} off={off}")
    return 1 if failed else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, UnicodeError, ValueError) as error:  # one line, never a Traceback
        print(f"SIM_CHECK: NOT_RUN {type(error).__name__}: {str(error)[:200]}")
        sys.exit(2)
