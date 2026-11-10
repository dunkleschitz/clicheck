# clicheck — zero-config CLI contract smoke tester

Point it at a command, get a pass/fail verdict on the universal CLI
contract. No test files to write.

```sh
clicheck mytool
clicheck python3 myscript.py --strict --json
clicheck -- git --checks help_exit,version_exit,noargs_finishes
```

## What it checks

Sixteen checks across six probes (all read-only; every probe runs with
stdin closed and a per-probe timeout):

| Probe | Input | Contract |
|---|---|---|
| `help` | `CMD --help` | exits 0, help text on stdout, stderr quiet (warn), mentions program name or "usage" (warn), no ANSI escapes when piped (warn) |
| `version` | `CMD --version` | exits 0, version on stdout, first line looks like name + version (warn), stderr quiet (warn) |
| `short_help` | `CMD -h` | behaves like `--help` (warn) |
| `usage_error` | `CMD --clicheck-no-such-flag` | exits nonzero, explains itself on stderr, keeps stdout quiet (warn); `--strict` additionally requires exit code 2 |
| `no_args` | `CMD </dev/null` | finishes within `--timeout` (a hang here is the failure an agent fears most); exit code is informational |
| `no_traceback` | all probes | no `Traceback (most recent call last)` leaks into any output |

Fail-level checks flip the exit code; warn-level checks are reported but
never fail the run alone.

Exit codes: `0` no failures · `1` one or more contract failures ·
`2` usage error (bad args, command not found).

Options: `--timeout SECS` (default 10, per probe), `--strict`,
`--json`, `--quiet` (failures and warnings only), `--checks a,b,c`,
`--list-checks`, `--version`.

## Why this exists

Testing frameworks (pytest, BATS, Scrut, expect) all require authored
tests. What was missing is the zero-config gate: one command that tells
you whether a CLI honors the conventions agents and scripts depend on —
help on stdout with exit 0, a parseable `--version`, usage errors that
are loud on stderr instead of silent on stdout, no hangs when stdin is
closed, no leaked tracebacks. Run it in CI as
`clicheck ./mytool || exit 1`.

Companion to `doccover` (which checks docs ↔ CLI surface): clicheck
checks binary ↔ universal contract, no docs needed.

## Examples

```sh
# Gate a release in CI: fail the pipeline on contract violations
clicheck ./mytool || exit 1

# Strict mode: usage errors must exit 2, not just nonzero
clicheck --strict ./mytool

# Check a command that needs fixed leading args
clicheck -- python3 scripts/deploy.py --checks help_exit,version_exit,noargs_finishes

# Machine-readable output for a dashboard
clicheck --json ./mytool | jq '.failures'

# What a failure looks like (a CLI whose --help exits 1):
# [FAIL] help_exit  --help exits 0 — rc=1
# 14 passed, 0 warnings, 1 failures
```

## Limitations

- clicheck judges the *contract*, not correctness: a `--help` that exits
  0 with plausible-looking but wrong text passes.
- The bare no-args probe runs the command's default behavior with stdin
  closed. Most CLIs print help or a usage error; a CLI whose default
  action is destructive or long-running should not be probed this way —
  use `--checks` to skip `noargs_finishes`.
- `usage_exit_2` (exit 2 on usage errors) is a convention, not a law:
  argparse/click follow it, many CLIs exit 1. That's why it's strict-only.
- Version "parseability" is a heuristic (`\d+\.\d+` in the first line),
  and `-h`/ANSI/name-mention checks are warn-level on purpose: real
  tools vary, and a contract checker that cries wolf is worse than none.
- Probes kill the direct child on timeout; grandchildren that detach
  could linger — another reason to only probe commands you trust.

## Trust and safety

clicheck **executes** the command with benign inputs only (`--help`,
`--version`, a bogus flag, and a bare run with stdin closed). Only run it
against commands you trust: a CLI that ignores `--help` could do
something else, and the bare no-args probe runs the command's default
behavior. Probes are time-bounded and stdin is always `/dev/null`, so
interactive prompts can't hang the run.

## Tests

```sh
python3 test_clicheck.py   # 18 tests, hermetic fixture CLIs
```

Fixtures cover: a contract-honoring CLI, broken `--version`, leaked
tracebacks, a bare-run hang, help-on-stderr, exit-1-on-usage (lenient OK,
strict FAIL), and ANSI in piped help.


## License

MIT — see [LICENSE](LICENSE).

## Pre-publish checklist

- [x] Tests green (18/18, Nov 9, 2026)
- [x] README + CHANGELOG + LICENSE (MIT) in place
- [x] Bench-audit A1–A7 clean (Nov 9, 2026 sweep; this section was the last gap)
- [x] Prepublish-check (stdlib-only, no secret-like literals) — clean, Nov 9, 2026 (scoped run)
- [x] CI workflow (.github/workflows/tests.yml) — added at prepublish
- [x] Publication blocker (Oct 25 git-history cleanse pattern gap) — cleared: full history re-checked Nov 9, 2026, 0 `godsby` hits, 0 `/home/hatch` hits
- [x] Sam's per-project publication approval (charter gate) — Tier A batch, overnight campaign Nov 9, 2026
