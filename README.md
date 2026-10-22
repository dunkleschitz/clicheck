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

## Pre-publish checklist

Per the project charter, nothing ships publicly until the maintainer
approves the publishing account/org and the license. Before
first publication:

1. **Secrets hygiene** — run a secrets scan over the repo and its history
   (`gitleaks detect --source .` or `trufflehog git file://.`), resolve
   every hit, and grep once more for obvious keys/tokens by hand.
2. **History review** — read `git log` and the full diff end-to-end; no
   credentials, private paths, or personal data may be committed.
3. **License** — replace the TBD notice with the maintainer-approved
   LICENSE file.
4. **Maintainer approval** — The maintainer signs off on this project's first
   public publication.

## License

TBD — pending maintainer approval (MIT proposed).
