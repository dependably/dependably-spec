# Dependably finding schema, v1

Normative contract for `--format json`. Every tool in the suite emits the same envelope, so a
CI job, a dashboard, or an AI consumer can parse any of them identically without knowing which
tool produced the output.

Key words follow RFC 2119.

This document was written after the fact, from six implementations that had agreed by
convention rather than by specification. §8 records where they disagree; those are defects to
be fixed against this document, not variations to be preserved.

## 1. Envelope

1.1. Output **MUST** be a single JSON object with exactly these six keys, in this order:

```json
{
  "tool": "pdbcheck",
  "toolVersion": "1.2.0",
  "schemaVersion": "1.0",
  "target": "artifacts/MyLib.1.0.0.nupkg",
  "summary": { },
  "findings": [ ]
}
```

1.2. `tool` **MUST** be the tool's command name — the same token it uses as its `.dependably`
section key.

1.3. `toolVersion` **MUST** be the released version, with any build-metadata suffix stripped.

1.4. `schemaVersion` **MUST** be the string `"1.0"` for this revision. It describes the
envelope, never the tool.

1.5. `target` **MUST** be what the user asked the tool to inspect, verbatim.

1.6. An optional seventh key, `extra`, **MAY** carry tool-specific data that is about the run
as a whole rather than about any one finding. No other top-level key is permitted.

1.7. All keys **MUST** be camelCase. No tool in this suite emits snake_case anywhere.

## 2. Summary

2.1. `summary` **MUST** contain exactly `scanned`, `findings`, `bySeverity`, and `exitCode`.

```json
"summary": {
  "scanned": 26,
  "findings": 45,
  "bySeverity": { "critical": 0, "high": 0, "moderate": 1, "low": 40, "info": 4 },
  "exitCode": 1
}
```

2.2. `scanned` **MUST** be the number of units the tool examined. What a unit is, is tool-defined
— a package, an assembly, a source file — and **SHOULD** be documented in the tool's README.

2.3. `findings` **MUST** equal the length of the top-level `findings` array, suppressed entries
included.

2.4. `bySeverity` **MUST** carry all five ladder keys, including zeroes, and each count **MUST**
be derived from the findings actually emitted. A tool **MUST NOT** hardcode a key to zero: a
hardcoded count is a second, independent statement of the mapping its findings already use, and
the two drift.

2.5. A tool whose internal model has fewer levels will legitimately report zero for a level it
cannot produce. It **MUST** document its producible range in its README. Promoting findings to
fill an unused level is worse than the zero — it trades a misleading count for a misleading
severity.

2.6. This leaves a consumer unable to distinguish "found no critical findings" from "does not
look for critical findings". The envelope has no way to express the difference and gaining one
would be a breaking change, so it is recorded here as a known limitation for a future revision
rather than papered over.

2.7. `exitCode` **MUST** equal the process's real exit code.

2.8. Consequently a tool **MUST** compute the gate before rendering, and pass the result to the
formatter rather than re-deriving it. A display filter can narrow what is printed without
changing what failed, so a re-derived value will disagree with reality precisely when it
matters most.

## 3. Findings

3.1. `findings` **MUST** be an array of objects, each with exactly these keys:

```json
{
  "severity": "high",
  "ruleId": "build-path-leak",
  "category": "disclosure",
  "message": "Assembly records the build machine's symbol path.",
  "location": { "file": "lib/net8.0/MyLib.dll", "line": null, "column": null },
  "remediation": "Set <ContinuousIntegrationBuild>true</ContinuousIntegrationBuild> on CI.",
  "suppressed": false,
  "suppressedBy": null,
  "extra": { }
}
```

3.2. `severity` **MUST** be a ladder word from §4.

3.3. `ruleId` **MUST** be an id from the tool's published rule registry, so a `.dependably`
`rules` entry or exception can name it. A tool **MUST** publish that registry in its README and
export it as a constant.

3.4. `category` groups related rules for display. The vocabulary is tool-defined; it **MUST** be
documented in the tool's README.

3.5. `message` **MUST** be human-readable and **MUST NOT** contain text read out of the artifact
under inspection. Untrusted content belongs in `location` or `extra`, where a consumer knows to
treat it as data.

3.6. `remediation` **SHOULD** be populated whenever the tool knows the fix, and **MUST** be
`null` otherwise. It is the field that turns a report into an action.

3.7. `extra` **MAY** carry tool-specific facts about this finding. It is the only sanctioned
place for them; a tool **MUST NOT** add a new key to the finding object instead.

3.8. `findings` **MUST** be complete and **MUST NOT** be truncated, even when human-readable
output is summarized or grouped. A consumer that counts or filters needs every entry.

## 4. Severity ladder

4.1. Five words, most severe first: `critical`, `high`, `moderate`, `low`, `info`. Ranks are
5 down to 1.

4.2. Inbound vocabulary maps on: `medium` to `moderate`, `error` to `high`, `warning` and `warn`
to `low`. An unrecognized value maps to `info`.

4.3. That leniency applies only to data being read. A **gate level** supplied by a user —
`--fail-on severity=<level>` or `failOn.severity` — **MUST** be parsed strictly and rejected
when unrecognized. Folding a typo to `info` silently widens the gate to everything, which is the
opposite of what the user asked for.

4.4. Tools **MUST** accept the `error`, `warning`, and `warn` aliases as gate levels.

## 5. Location

5.1. `location` **MUST** be present on every finding.

5.2. It **MUST** be either `null`, for a finding that is not anchored to a file at all, or an
object with `file`, `line`, and `column`, each independently nullable.

5.3. A tool whose findings are mostly file-anchored **SHOULD** always emit the object form and
null the members it lacks, so consumers never have to branch on the field's type.

## 6. Suppression

6.1. A finding suppressed by a `.dependably` exception **MUST** appear in `findings` with
`suppressed: true` and `suppressedBy` set to the exception's `reason`.

6.2. A suppressed finding **MUST NOT** be dropped. An exception records an accepted risk; erasing
it makes an accepted finding indistinguishable from a rule that never fired, and the acceptance
stops being reviewable.

6.3. A suppressed finding **MUST NOT** contribute to the gate, but **MUST** be counted in
`summary.findings` and `summary.bySeverity`.

6.4. A rule set to `off` is different: its findings are not produced at all and **MUST NOT**
appear. `off` means the rule does not apply here; an exception means this specific finding is
accepted, for a stated reason, and stays visible.

## 7. Exit codes

| Code | Meaning |
|------|---------|
| `0`  | Clean — nothing at or above the gate threshold. Also `--help` and `--version`. |
| `1`  | A finding tripped the gate. |
| `2`  | Usage error, or an operational failure such as an unreadable input or a malformed config. |

7.1. A malformed `.dependably` **MUST** exit `2`, never `1`. A config error is not a finding.

7.2. A display filter (`--severity`) **MUST NOT** affect the exit code, and the tool **SHOULD**
report how many findings it hid so a narrowed view cannot read as a clean one.

## 8. Known divergences

Defects against this document, recorded so they are fixed rather than copied:

| Tool | Divergence |
|------|-----------|
| nucheck | Drops suppressed findings entirely instead of emitting them with `suppressed`/`suppressedBy` (§6.1). Rejects the `error`/`warning`/`warn` gate aliases (§4.4). |
| cslint | Omits `extra` on findings. Its `bySeverity` is now a histogram of emitted findings (§2.4), but `critical` and `moderate` stay zero because its three internal levels map to `high`/`low`/`info` — permitted by §2.5, and an instance of the limitation in §2.6. |
| codemetrics | Omits `extra` on findings; uses envelope-level `extra` for its metrics tree, which is permitted by §1.6. Cannot satisfy §6 at all: its exceptions apply to per-metric threshold violations while its `findings` array holds interpreted diagnoses, so the suppressible unit and the reported unit are different objects. `suppressed` is emitted as a constant `false`. Closing this needs either metric violations emitted as findings or an exception-aware severity gate. |

## 9. Versioning

9.1. `schemaVersion` changes only when the envelope changes.

9.2. Adding a key to `extra`, adding a rule id, or adding a category is **not** a schema change.

9.3. Removing or renaming an envelope or finding key, or changing the ladder, **is** a breaking
change and requires a major revision of this document.
