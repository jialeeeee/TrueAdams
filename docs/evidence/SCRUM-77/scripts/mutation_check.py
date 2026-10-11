"""Mutation check: break the code one way at a time and confirm the tests catch it.

Run from the repo root:
    python mutation_check.py <mutations file> backend|frontend

The mutations file defines BACKEND_TESTS (unittest module names), FRONTEND_TESTS
(Vitest file paths, relative to frontend/) and MUTATIONS, a list of
(id, side, description, traces, path, old text, new text). Each mutation replaces
`old` (which must appear exactly once) with `new`, runs that side's tests, and
restores the file byte for byte, even if the run fails.
"""
import importlib.util
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path.cwd()
PY = ROOT / "backend/.venv/Scripts/python.exe"  # Windows venv layout


def load(path):
    spec = importlib.util.spec_from_file_location("mutations", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run_backend(config):
    r = subprocess.run([str(PY), "-m", "unittest", *config.BACKEND_TESTS],
                       cwd=ROOT / "backend", capture_output=True, text=True)
    out = r.stdout + r.stderr
    failed = sorted(set(re.findall(r"^(?:FAIL|ERROR): (test_\w+)", out, re.M)))
    return r.returncode, failed, out


def run_frontend(config):
    r = subprocess.run("npx vitest run " + " ".join(config.FRONTEND_TESTS),
                       cwd=ROOT / "frontend", capture_output=True, text=True, shell=True,
                       encoding="utf-8", errors="replace")
    out = re.sub(r"\x1b\[[0-9;]*m", "", r.stdout + r.stderr)
    failed = sorted(set(m.strip() for m in
                        re.findall(r"^\s*(?:×|FAIL)\s+.*?> ([^>]+?)(?:\s+\d+ms)?$", out, re.M)))
    return r.returncode, failed, out


def main(config_path, side):
    config = load(config_path)
    runner = run_backend if side == "backend" else run_frontend
    code, _, out = runner(config)
    if code != 0:
        print("BASELINE FAILS — fix before mutating\n", out[-3000:])
        sys.exit(1)
    print(f"baseline: all {side} tests pass")
    for mid, mside, what, traces, path, old, new in config.MUTATIONS:
        if mside != side:
            continue
        file = ROOT / path
        original = file.read_bytes()
        text = original.decode("utf-8")
        if "\r\n" in text:  # Windows checkouts (core.autocrlf) use CRLF line endings
            old, new = old.replace("\n", "\r\n"), new.replace("\n", "\r\n")
        if text.count(old) != 1:
            print(f"{mid} | {what} | SKIPPED — pattern found {text.count(old)} times")
            continue
        try:
            file.write_bytes(text.replace(old, new).encode("utf-8"))
            code, failed, _ = runner(config)
        finally:
            file.write_bytes(original)
        print(f"{mid} | {what} | {traces} | {'CAUGHT' if code else 'MISSED'} | "
              f"{', '.join(failed) or '-'}")
    code, _, _ = runner(config)
    print("after restore:", "all pass" if code == 0 else "FAILING — check files")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
