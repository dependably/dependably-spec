#!/usr/bin/env python3
"""Validate the conformance corpus and schema against the spec document.

The registries this checks against are parsed out of docs/dependably-config-spec.md rather
than restated here. A validator carrying its own copy of the rules is a second source of
truth, and it drifts from the document the moment either is edited.

Exit 0 when everything agrees, 1 with a list of problems otherwise.
"""

import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
SPEC = ROOT / "docs" / "dependably-config-spec.md"
SCHEMA = ROOT / "schema" / "dependably-v1.json"
CASES = ROOT / "conformance" / "dependably" / "cases"

# Prefixes the corpus README documents. A new group is a deliberate act, not a typo.
KNOWN_PREFIXES = ("discovery-", "sections-", "merge-", "exceptions-", "validation-")

problems: list[str] = []


def fail(message: str) -> None:
    problems.append(message)


def section(text: str, number: str) -> str:
    """The body of a numbered top-level section, up to the next one or end of document."""
    match = re.search(rf"^## {number}\..*?$(.*?)(?=^## \d+\.|\Z)", text, re.M | re.S)
    return match.group(1) if match else ""


def parse_registries(text: str) -> tuple[set[str], set[str], set[str]]:
    """Error codes (§10), warning codes (§11), and tool section keys (§3.3)."""
    errors = set(re.findall(r"`([A-Z][A-Z_]+)`", section(text, "10")))
    warnings = set(re.findall(r"\|\s*`([A-Z][A-Z_]+)`\s*\|", section(text, "11")))

    # Both the canonical key and any deprecated alias are valid section names, so the schema
    # is right to declare both and the validator has to know about both.
    tools = set()
    for row in re.findall(r"^\s*\|\s*([a-z][\w-]*)\s*\|\s*`([^`]+)`\s*\|([^|]*)\|", text, re.M):
        tools.add(row[1])
        alias = re.search(r"`([^`]+)`", row[2])
        if alias:
            tools.add(alias.group(1))

    return errors, warnings, tools


def main() -> int:
    if not SPEC.exists():
        print(f"missing spec document: {SPEC}", file=sys.stderr)
        return 1

    spec_text = SPEC.read_text()
    errors, warnings, tools = parse_registries(spec_text)

    for name, values in (("error", errors), ("warning", warnings), ("tool", tools)):
        if not values:
            fail(f"parsed no {name} registry from the spec — the document's shape changed")

    # The schema is editor tooling, but a schema that does not parse helps nobody.
    try:
        schema = json.loads(SCHEMA.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        fail(f"schema/dependably-v1.json is not readable JSON: {exc}")
        schema = {}

    # Every tool the spec registers must be addressable in the schema, or an editor will
    # redline a section the spec says is valid.
    schema_sections = set(schema.get("properties", {})) - {"$schema", "version", "common"}
    for tool in sorted(tools - schema_sections):
        fail(f"tool '{tool}' is in the spec's §3.3 registry but not in the JSON schema")
    for extra in sorted(schema_sections - tools):
        fail(f"schema declares section '{extra}', which the spec's §3.3 registry does not list")

    case_files = sorted(CASES.glob("*.json"))
    if not case_files:
        fail("no conformance cases found")

    seen_names: dict[str, str] = {}

    for path in case_files:
        try:
            case = json.loads(path.read_text())
        except json.JSONDecodeError as exc:
            fail(f"{path.name}: invalid JSON ({exc})")
            continue

        for key in ("name", "description", "tool", "files", "expect"):
            if key not in case:
                fail(f"{path.name}: missing required key '{key}'")

        name = case.get("name")
        if name and name != path.stem:
            fail(f"{path.name}: name '{name}' does not match the filename")
        if name in seen_names:
            fail(f"{path.name}: duplicate case name, also used by {seen_names[name]}")
        elif name:
            seen_names[name] = path.name

        if not path.name.startswith(KNOWN_PREFIXES):
            fail(f"{path.name}: filename does not start with a documented group prefix")

        tool = case.get("tool")
        if tool and tool not in tools:
            fail(f"{path.name}: tool '{tool}' is not in the spec's §3.3 registry")

        if "description" in case and not str(case["description"]).strip():
            fail(f"{path.name}: description is empty")

        expect = case.get("expect")
        if not isinstance(expect, dict):
            if "expect" in case:
                fail(f"{path.name}: expect must be an object")
            continue

        code = expect.get("error")
        if code and code not in errors:
            fail(f"{path.name}: expects error '{code}', which is not in the §10 registry")

        for code in expect.get("warnings") or []:
            if code not in warnings:
                fail(f"{path.name}: expects warning '{code}', which is not in the §11 registry")

        # A case that asserts nothing passes vacuously and protects nothing.
        if not expect:
            fail(f"{path.name}: expect is empty, so the case asserts nothing")

    if problems:
        print(f"{len(problems)} problem(s):\n", file=sys.stderr)
        for problem in problems:
            print(f"  - {problem}", file=sys.stderr)
        return 1

    print(
        f"OK: {len(case_files)} cases, {len(tools)} tools, "
        f"{len(errors)} error codes, {len(warnings)} warning codes."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
