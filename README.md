# dependably-spec

The normative contract shared by the Dependably tool suite: the `.dependably` config format,
the finding schema every tool emits, and the cross-language conformance corpus that pins both.

This repository holds no implementation. It exists so the contract has a home that is not one
of the tools bound by it — previously it lived inside npm-check, which meant one implementation
owned the rules for six, a spec change had to be filed against a peer, and drift between vendored
copies was invisible.

## Contents

| Path | What it is |
|------|-----------|
| [`docs/dependably-config-spec.md`](docs/dependably-config-spec.md) | **Normative.** The `.dependably` runtime contract: discovery, sections, merge, rules, exceptions, gate. |
| [`docs/finding-schema.md`](docs/finding-schema.md) | **Normative.** The `--format json` envelope every tool emits. |
| [`schema/dependably-v1.json`](schema/dependably-v1.json) | JSON Schema for editor completion. **Not authoritative** — where it disagrees with the spec, the spec wins. |
| [`conformance/dependably/`](conformance/dependably/) | Language-neutral fixtures pinning the config contract. |

## Tools bound by this contract

| Tool | Language | Section key |
|------|----------|-------------|
| npm-check | JavaScript | `npm-check` |
| nucheck | C# | `nucheck` |
| pycheck | Python | `pycheck` |
| cslint | C# | `cslint` |
| codemetrics | C# | `codemetrics` |
| pdbcheck | C# | `pdbcheck` |

A tool's section key is always its command name.

## Vendoring

Tools vendor `conformance/dependably/` and replay it through a thin per-language adapter. Copy
it; do not fork it. Record the commit you copied in a `VENDOR.md` beside the copy so drift is
detectable:

```
tests/<project>/conformance/dependably/   ← the copy
tests/<project>/conformance/VENDOR.md     ← upstream URL + commit SHA + sync command
```

The corpus is data, not code, so a tool at an older commit is not broken — it is testing an
older contract. `VENDOR.md` is what makes the difference visible rather than silent.

### Replaying a case as your own tool

Most cases carry `"tool": "$any"`. Their section key, alias key and rule ids are placeholders,
and an adapter binds them to its own names before the case runs — so the case exercises the
adapter's tool rather than the tool it happened to be written next to. Spec §12 is the
normative contract; `conformance/dependably/README.md` is the adapter's copy of it.

The remaining cases name a tool in their `tool` field and carry literal vocabulary, with the
reason in the corpus README. An adapter for a different tool replays their **grammar**, not
that tool's selector applicability: selectors are validated before the expiry format is, so
replaying a `package`-selector case under a tool that emits no `package` raises a selector
error and fails a case that is actually passing. Applicability is per-tool and belongs in each
tool's own tests.

## Adding a tool

1. Add a row to §3.3 of the config spec and to the table above. The section key **is** the
   command name; a new tool takes no deprecated alias, since aliases exist only for tools that
   predate this format.
2. Add the section to `schema/dependably-v1.json`.
3. Publish the tool's rule-id registry in its README and export it as a constant.
4. Vendor the corpus and wire up an adapter, including the §12 binding map. A new tool binds
   no `$alias` and skips the cases that require one.

## Changing the contract

A change lands here first, then in the implementations. Widening is cheap; narrowing is not — a
tool at an older vendored commit must keep passing, so prefer adding a case over changing one.

Breaking changes to the finding envelope require a `schemaVersion` bump and a coordinated
release across every tool.

## License

Apache-2.0.
