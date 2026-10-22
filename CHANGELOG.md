# CHANGELOG — clicheck

## 1.0.0 (2026-10-22)

Initial release.

- Sixteen checks across six probes: `--help`, `--version`, `-h`,
  bogus-flag usage error, bare invocation with stdin closed, and a
  traceback-leak scan over all captured output.
- Fail/warn severity split: fail-level checks (help/version exit 0 on
  stdout, nonzero usage errors, no hangs, no tracebacks) flip the exit
  code; warn-level checks (stderr quiet, name/usage mention, no piped
  ANSI, parseable version line, `-h` parity) are reported only.
- `--strict` requires exit code 2 on usage errors; default lenient mode
  accepts any nonzero exit.
- `--timeout` per probe (default 10s), stdin always `/dev/null`,
  `--checks` subset selection, `--list-checks`, `--json`, `--quiet`.
- Exit codes 0 clean / 1 contract failures / 2 usage error.
- Dogfooded on the 13-tool bench plus git/ls/curl/python3: zero false
  positives; one benign warn (sandbox-physical prints usage to stdout
  on unknown flags).
