#!/usr/bin/env python3
"""Tests for clicheck — run with: python3 test_clicheck.py"""
import json
import os
import subprocess
import sys
import tempfile
import unittest

CLICHECK = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "clicheck.py")

GOOD = '''
import argparse
ap = argparse.ArgumentParser(prog="good")
ap.add_argument("--version", action="version", version="good 1.2.3")
ap.add_argument("--thing")
a = ap.parse_args()
print("ran with", a.thing)
'''

NO_VERSION = '''
import argparse, sys
ap = argparse.ArgumentParser(prog="noversion")
if "--version" in sys.argv:
    print("no version here", file=sys.stderr); sys.exit(1)
a = ap.parse_args()
print("ok")
'''

TRACEBACK_CLI = '''
import argparse, sys
ap = argparse.ArgumentParser(prog="tracebackcli")
if "--clicheck-no-such-flag" in sys.argv:
    raise RuntimeError("boom: unhandled")
ap.add_argument("--version", action="version", version="tracebackcli 0.1")
ap.parse_args()
print("ok")
'''

HANG_CLI = '''
import argparse, sys, time
ap = argparse.ArgumentParser(prog="hangcli")
ap.add_argument("--version", action="version", version="hangcli 0.1")
a = ap.parse_args()
time.sleep(60)
print("done")
'''

STDERR_HELP = '''
import sys
if "--help" in sys.argv or "-h" in sys.argv:
    print("usage: stderrhelp", file=sys.stderr); sys.exit(0)
if "--version" in sys.argv:
    print("stderrhelp 2.0"); sys.exit(0)
print("ran")
'''

EXIT1_USAGE = '''
import argparse, sys
ap = argparse.ArgumentParser(prog="exit1usage")
ap.add_argument("--version", action="version", version="exit1usage 3.0")
try:
    ap.parse_args()
except SystemExit as e:
    sys.exit(1 if e.code else 0)  # normalize usage errors to 1, keep --help at 0
print("ok")
'''

ANSI_HELP = '''
import sys
if "--help" in sys.argv:
    print("\\x1b[1mansihelp\\x1b[0m - does things"); sys.exit(0)
if "--version" in sys.argv:
    print("ansihelp 1.0"); sys.exit(0)
if "--clicheck-no-such-flag" in sys.argv:
    print("ansihelp: unknown flag", file=sys.stderr); sys.exit(2)
print("ran")
'''


def run_clicheck(cmd_argv, *extra):
    r = subprocess.run(
        [sys.executable, CLICHECK, *extra, "--", *cmd_argv],
        capture_output=True, text=True, timeout=120)
    return r


def results_of(cmd_argv, *extra):
    r = run_clicheck(cmd_argv, *extra, "--json")
    assert r.returncode in (0, 1), r.stderr
    return json.loads(r.stdout), r


class ClicheckTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.bin = {}
        for name, src in [("good", GOOD), ("noversion", NO_VERSION),
                          ("tracebackcli", TRACEBACK_CLI),
                          ("hangcli", HANG_CLI),
                          ("stderrhelp", STDERR_HELP),
                          ("exit1usage", EXIT1_USAGE),
                          ("ansihelp", ANSI_HELP)]:
            p = os.path.join(cls.tmp.name, name + ".py")
            with open(p, "w") as f:
                f.write(src)
            cls.bin[name] = [sys.executable, p]

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def by_id(self, data):
        return {r["id"]: r for r in data["results"]}

    def test_good_cli_passes(self):
        data, r = results_of(self.bin["good"])
        self.assertEqual(r.returncode, 0)
        self.assertEqual(data["failures"], 0)

    def test_broken_version_fails(self):
        data, r = results_of(self.bin["noversion"])
        by = self.by_id(data)
        self.assertFalse(by["version_exit"]["ok"])
        self.assertFalse(by["version_stdout"]["ok"])
        self.assertEqual(r.returncode, 1)

    def test_traceback_detected(self):
        data, r = results_of(self.bin["tracebackcli"])
        by = self.by_id(data)
        self.assertFalse(by["no_traceback"]["ok"])
        self.assertEqual(r.returncode, 1)

    def test_hang_fails_noargs(self):
        data, r = results_of(self.bin["hangcli"], "--timeout", "1")
        by = self.by_id(data)
        self.assertFalse(by["noargs_finishes"]["ok"])
        self.assertIn("timed out", by["noargs_finishes"]["detail"])
        self.assertEqual(r.returncode, 1)
        # but --help/--version probes still passed (fast paths)
        self.assertTrue(by["help_exit"]["ok"])
        self.assertTrue(by["version_exit"]["ok"])

    def test_help_on_stderr_is_warn_only(self):
        data, r = results_of(self.bin["stderrhelp"])
        by = self.by_id(data)
        self.assertFalse(by["help_stdout"]["ok"])      # fail: nothing on stdout
        self.assertFalse(by["help_not_stderr"]["ok"])  # warn only
        self.assertEqual(by["help_not_stderr"]["severity"], "warn")
        self.assertEqual(r.returncode, 1)  # failed on help_stdout, not the warn

    def test_exit1_usage_lenient_ok_strict_fails(self):
        data, r = results_of(self.bin["exit1usage"])
        by = self.by_id(data)
        self.assertTrue(by["usage_nonzero"]["ok"])
        self.assertEqual(r.returncode, 0)
        data2, r2 = results_of(self.bin["exit1usage"], "--strict")
        by2 = self.by_id(data2)
        self.assertFalse(by2["usage_exit_2"]["ok"])
        self.assertEqual(r2.returncode, 1)

    def test_ansi_in_piped_help_warns(self):
        data, r = results_of(self.bin["ansihelp"])
        by = self.by_id(data)
        self.assertFalse(by["help_no_ansi"]["ok"])
        self.assertEqual(by["help_no_ansi"]["severity"], "warn")
        self.assertEqual(r.returncode, 0)  # warn doesn't fail the run

    def test_missing_command_exit_2(self):
        r = run_clicheck(["/nonexistent/definitely-not-here"])
        self.assertEqual(r.returncode, 2)
        self.assertIn("not found", r.stderr)

    def test_no_command_exit_2(self):
        r = subprocess.run([sys.executable, CLICHECK],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 2)

    def test_unknown_check_id_exit_2(self):
        r = run_clicheck(self.bin["good"], "--checks", "bogus_check")
        self.assertEqual(r.returncode, 2)

    def test_checks_subset(self):
        data, r = results_of(self.bin["good"], "--checks", "help_exit,version_exit")
        self.assertEqual(len(data["results"]), 2)
        self.assertEqual(r.returncode, 0)

    def test_list_checks(self):
        r = subprocess.run([sys.executable, CLICHECK, "--list-checks"],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0)
        self.assertIn("help_exit", r.stdout)
        self.assertIn("no_traceback", r.stdout)

    def test_version_flag(self):
        r = subprocess.run([sys.executable, CLICHECK, "--version"],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0)
        self.assertIn("1.0.0", r.stdout)

    def test_json_shape(self):
        data, r = results_of(self.bin["good"])
        self.assertIn("results", data)
        for res in data["results"]:
            self.assertEqual(set(res.keys()),
                             {"id", "severity", "ok", "desc", "detail"})
            self.assertIn(res["severity"], ("fail", "warn"))
            self.assertIsInstance(res["ok"], bool)

    def test_quiet_hides_passes(self):
        r = run_clicheck(self.bin["ansihelp"], "--quiet")
        self.assertNotIn("[ok  ]", r.stdout)
        self.assertIn("help_no_ansi", r.stdout)

    def test_human_output_summary_line(self):
        r = run_clicheck(self.bin["good"])
        self.assertIn("passed", r.stdout)
        self.assertIn("failures", r.stdout)

    def test_negative_timeout_rejected(self):
        r = run_clicheck(self.bin["good"], "--timeout", "-1")
        self.assertEqual(r.returncode, 2)

    def test_good_cli_noargs_informational(self):
        # argparse with no required args: bare run exits 0; recorded, not judged
        data, _ = results_of(self.bin["good"])
        by = self.by_id(data)
        self.assertTrue(by["noargs_finishes"]["ok"])
        self.assertIn("rc=0", by["noargs_finishes"]["detail"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
