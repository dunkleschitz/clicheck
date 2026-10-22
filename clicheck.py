#!/usr/bin/env python3
"""clicheck — zero-config CLI contract smoke tester.

Point it at a command, get a pass/fail verdict on the universal CLI
contract: --help and --version behave, usage errors are loud on stderr,
nothing hangs, nothing leaks a traceback. No test files to write.

    clicheck mytool
    clicheck python3 myscript.py --strict --json

Probes run (all read-only, no side effects beyond what the command itself
does on these inputs):
  help         CMD --help            -> exit 0, help text on stdout
  version      CMD --version         -> exit 0, parseable version on stdout
  short_help   CMD -h                -> behaves like --help (warn-level)
  usage_error  CMD --<bogus-flag>    -> nonzero exit, diagnostics on stderr
  no_args      CMD </dev/null        -> finishes within --timeout, no hang
  (every probe is also scanned for leaked tracebacks)

Exit codes: 0 = no failures; 1 = one or more contract failures;
2 = usage error (bad args, command not found).

Safety: clicheck EXECUTES the command with benign inputs only
(--help, --version, a bogus flag, bare with stdin closed). Only run it
against commands you trust: a CLI that ignores --help could do something
else, and the bare no-args probe will run the command's default behavior
with stdin closed. Every probe is time-bounded (--timeout, default 10s)
and stdin is always /dev/null so interactive prompts can't hang the run.

Stdlib only.
"""
import argparse
import json
import os
import re
import subprocess
import sys

VERSION = "1.0.0"

DEFAULT_TIMEOUT = 10
BOGUS_FLAG = "--clicheck-no-such-flag"

TRACEBACK_RE = re.compile(r"Traceback \(most recent call last\)")
VERSION_RE = re.compile(r"\d+\.\d+")
ANSI_RE = re.compile(r"\x1b\[")

# check id -> (severity, description); severity "fail" flips the exit code,
# "warn" is reported but never fails the run on its own.
CHECKS = {
    "help_exit": ("fail", "--help exits 0"),
    "help_stdout": ("fail", "--help prints help text on stdout"),
    "help_not_stderr": ("warn", "--help keeps stderr quiet"),
    "help_mentions_name": ("warn", "--help mentions the program name or usage"),
    "help_no_ansi": ("warn", "--help has no ANSI escapes when piped"),
    "version_exit": ("fail", "--version exits 0"),
    "version_stdout": ("fail", "--version prints on stdout"),
    "version_parseable": ("warn", "--version first line looks like name + version"),
    "version_not_stderr": ("warn", "--version keeps stderr quiet"),
    "short_help": ("warn", "-h behaves like --help"),
    "usage_nonzero": ("fail", "unknown flag exits nonzero"),
    "usage_stderr": ("fail", "unknown flag explains itself on stderr"),
    "usage_stdout_quiet": ("warn", "unknown flag keeps stdout quiet"),
    "usage_exit_2": ("fail", "unknown flag exits 2 (strict contract)"),
    "noargs_finishes": ("fail", "bare invocation finishes within timeout"),
    "no_traceback": ("fail", "no leaked tracebacks in any probe output"),
}


class UsageError(Exception):
    pass


def run_probe(argv, timeout):
    """Run argv with stdin closed; return (rc, stdout, stderr, timed_out)."""
    try:
        p = subprocess.run(
            argv,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return p.returncode, p.stdout, p.stderr, False
    except FileNotFoundError:
        raise UsageError(f"command not found: {argv[0]}")
    except subprocess.TimeoutExpired as e:
        out = (e.stdout or "") if isinstance(e.stdout, str) else ""
        err = (e.stderr or "") if isinstance(e.stderr, str) else ""
        return None, out, err, True
    except OSError as e:
        raise UsageError(f"could not run {' '.join(argv)}: {e}")


def prog_name(argv):
    base = os.path.basename(argv[0])
    if base == "python3" and len(argv) > 1 and argv[1].endswith(".py"):
        base = os.path.basename(argv[1])
    return base


def check(cmd_argv, timeout, strict, selected):
    """Run probes; return list of (check_id, ok, detail) dicts."""
    name = prog_name(cmd_argv)
    results = []

    def rec(cid, ok, detail=""):
        if selected is not None and cid not in selected:
            return
        results.append(
            {"id": cid, "severity": CHECKS[cid][0], "ok": bool(ok),
             "desc": CHECKS[cid][1], "detail": detail}
        )

    # --help
    rc, out, err, timed_out = run_probe(cmd_argv + ["--help"], timeout)
    help_ok = not timed_out
    rec("help_exit", help_ok and rc == 0,
        f"rc={rc}" if help_ok else f"timed out after {timeout}s")
    rec("help_stdout", help_ok and bool(out.strip()),
        f"{len(out)} bytes on stdout" if help_ok else "no output (timeout)")
    rec("help_not_stderr", help_ok and not err.strip(),
        f"{len(err)} bytes on stderr" if help_ok and err.strip() else "")
    rec("help_mentions_name",
        help_ok and (name.lower() in out.lower() or "usage" in out.lower()),
        "" if not help_ok else "name/usage not found in help text")
    rec("help_no_ansi", help_ok and not ANSI_RE.search(out),
        "ANSI escapes present in piped --help" if help_ok and ANSI_RE.search(out) else "")

    # --version
    rc, vout, verr, timed_out = run_probe(cmd_argv + ["--version"], timeout)
    ver_ok = not timed_out
    rec("version_exit", ver_ok and rc == 0,
        f"rc={rc}" if ver_ok else f"timed out after {timeout}s")
    rec("version_stdout", ver_ok and bool(vout.strip()),
        f"{len(vout)} bytes on stdout" if ver_ok else "no output (timeout)")
    first = vout.strip().splitlines()[0] if vout.strip() else ""
    rec("version_parseable", ver_ok and bool(VERSION_RE.search(first)),
        f"first line: {first[:80]!r}" if ver_ok and not VERSION_RE.search(first) else "")
    rec("version_not_stderr", ver_ok and not verr.strip(),
        f"{len(verr)} bytes on stderr" if ver_ok and verr.strip() else "")

    # -h
    rc, hout, herr, timed_out = run_probe(cmd_argv + ["-h"], timeout)
    rec("short_help", (not timed_out) and rc == 0 and bool(hout.strip()),
        f"rc={rc}" if not timed_out else f"timed out after {timeout}s")

    # bogus flag
    rc, uout, uerr, timed_out = run_probe(cmd_argv + [BOGUS_FLAG], timeout)
    use_ok = not timed_out
    rec("usage_nonzero", use_ok and rc not in (None, 0),
        f"rc={rc}" if use_ok else f"timed out after {timeout}s")
    rec("usage_stderr", use_ok and bool(uerr.strip()),
        "nothing on stderr" if use_ok and not uerr.strip() else "")
    rec("usage_stdout_quiet", use_ok and not uout.strip(),
        f"{len(uout)} bytes on stdout" if use_ok and uout.strip() else "")
    if strict:
        rec("usage_exit_2", use_ok and rc == 2,
            f"rc={rc} (strict contract wants 2)" if use_ok else "")

    # bare invocation, stdin closed
    rc, nout, nerr, timed_out = run_probe(cmd_argv, timeout)
    rec("noargs_finishes", not timed_out,
        f"timed out after {timeout}s (hung with stdin closed)"
        if timed_out else f"rc={rc}")

    # traceback scan over everything captured
    all_text = "\n".join([out, err, vout, verr, hout, herr, uout, uerr,
                          nout, nerr])
    rec("no_traceback", not TRACEBACK_RE.search(all_text),
        "traceback leaked into output" if TRACEBACK_RE.search(all_text) else "")

    return results


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="clicheck",
        description="Zero-config CLI contract smoke tester: probe a command's "
                    "--help/--version/usage-error/no-args behavior and report "
                    "contract deviations. Exit 0 = no failures, 1 = failures, "
                    "2 = usage error.")
    ap.add_argument("command", nargs=argparse.REMAINDER,
                    help="command (plus fixed args) to check, e.g. "
                         "clicheck mytool  or  clicheck python3 myscript.py")
    ap.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT,
                    help=f"seconds per probe (default {DEFAULT_TIMEOUT})")
    ap.add_argument("--strict", action="store_true",
                    help="enforce the strict contract: usage errors exit 2")
    ap.add_argument("--json", action="store_true",
                    help="emit machine-readable results on stdout")
    ap.add_argument("--quiet", action="store_true",
                    help="only print failures and warnings")
    ap.add_argument("--checks",
                    help="comma-separated subset of check ids to run "
                         "(see --list-checks)")
    ap.add_argument("--list-checks", action="store_true",
                    help="list check ids and exit")
    ap.add_argument("--version", action="version", version=f"%(prog)s {VERSION}")
    args = ap.parse_args(argv)

    if args.list_checks:
        for cid, (sev, desc) in CHECKS.items():
            print(f"{cid:20} [{sev:4}] {desc}")
        return 0

    if not args.command or args.command[0] == "--":
        # argparse.REMAINDER keeps a leading "--" separator if given.
        cmd = [c for c in args.command if c != "--"]
    else:
        cmd = list(args.command)
    if not cmd:
        print("clicheck: no command given", file=sys.stderr)
        return 2
    if args.timeout <= 0:
        print("clicheck: --timeout must be positive", file=sys.stderr)
        return 2

    selected = None
    if args.checks:
        selected = {c.strip() for c in args.checks.split(",") if c.strip()}
        unknown = selected - set(CHECKS)
        if unknown:
            print(f"clicheck: unknown check ids: {', '.join(sorted(unknown))}",
                  file=sys.stderr)
            return 2

    try:
        results = check(cmd, args.timeout, args.strict, selected)
    except UsageError as e:
        print(f"clicheck: {e}", file=sys.stderr)
        return 2

    failures = [r for r in results if r["severity"] == "fail" and not r["ok"]]
    warns = [r for r in results if r["severity"] == "warn" and not r["ok"]]
    passed = [r for r in results if r["ok"]]
    rc = 1 if failures else 0

    if args.json:
        print(json.dumps({
            "command": cmd, "strict": args.strict,
            "failures": len(failures), "warnings": len(warns),
            "passed": len(passed), "results": results,
        }, indent=2))
    else:
        for r in results:
            if r["ok"] and args.quiet:
                continue
            mark = "ok  " if r["ok"] else ("FAIL" if r["severity"] == "fail" else "warn")
            line = f"[{mark}] {r['id']:20} {r['desc']}"
            if r["detail"]:
                line += f" — {r['detail']}"
            print(line)
        print(f"\n{len(passed)} passed, {len(warns)} warnings, "
              f"{len(failures)} failures")

    return rc


if __name__ == "__main__":
    sys.exit(main())
