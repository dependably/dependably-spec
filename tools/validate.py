#!/usr/bin/env python3
"""Validate the conformance corpus and schema against the spec document.

The registries this checks against are parsed out of docs/dependably-config-spec.md rather
than restated here. A validator carrying its own copy of the rules is a second source of
truth, and it drifts from the document the moment either is edited. The same applies to the
list of tool-specific cases, which is parsed out of the corpus README where adapter authors
read it.

Exit 0 when everything agrees, 1 with a list of problems otherwise.
"""

import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
SPEC = ROOT / "docs" / "dependably-config-spec.md"
SCHEMA = ROOT / "schema" / "dependably-v1.json"
CORPUS = ROOT / "conformance" / "dependably"
CASES = CORPUS / "cases"
CORPUS_README = CORPUS / "README.md"

# Prefixes the corpus README documents. A new group is a deliberate act, not a typo.
KNOWN_PREFIXES = ("discovery-", "sections-", "merge-", "exceptions-", "validation-")

# The `tool` value that marks a case as vocabulary-bound rather than authored for one tool.
ANY_TOOL = "$any"

# A configuration key that happens to start with `$`. It is never a placeholder.
CONFIG_DOLLAR_KEYS = {"$schema"}

# The subtrees of a case that carry tool vocabulary. `name` and `description` are prose and
# may legitimately mention a tool by name.
VOCABULARY_SUBTREES = ("files", "cli", "findings", "expect")

problems: list[str] = []


def fail(message: str) -> None:
    problems.append(message)


def section(text: str, number: str) -> str:
    """The body of a numbered top-level section, up to the next one or end of document."""
    match = re.search(rf"^## {number}\..*?$(.*?)(?=^## \d+\.|\Z)", text, re.M | re.S)
    return match.group(1) if match else ""


def named_section(text: str, title: str) -> str:
    """The body of a titled `##` section, up to the next one or end of document."""
    match = re.search(rf"^## {re.escape(title)}\s*$(.*?)(?=^## |\Z)", text, re.M | re.S)
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


def parse_binding_registries(text: str) -> tuple[set[str], set[str]]:
    """Vocabulary placeholders and applicability capabilities (§12)."""
    body = section(text, "12")
    placeholders = set(re.findall(r"^\|\s*`(\$[A-Za-z][A-Za-z0-9]*)`\s*\|", body, re.M))
    capabilities = set(re.findall(r"^\|\s*`([a-z][A-Za-z0-9]*)`\s*\|", body, re.M))
    return placeholders, capabilities


def parse_legacy_keys(text: str) -> set[str]:
    """Per-tool legacy config keys (§7.1).

    These are one tool's vocabulary, so a vocabulary-bound case must reach them through
    `$foreignKey` rather than naming one — the tool that owns the key would read it.
    """
    keys = set()
    for row in re.findall(r"^\s*\|\s*([^|]+)\|", section(text, "7"), re.M):
        for span in re.findall(r"`([^`]+)`", row):
            name = span.split(":")[0].strip()
            if re.fullmatch(r"[A-Za-z][A-Za-z0-9]*", name):
                keys.add(name)
    return keys


def parse_tool_specific_table(text: str) -> dict[str, tuple[str, str]]:
    """Case name -> (tool, reason) from the corpus README's tool-specific table."""
    body = named_section(text, "Tool-specific cases")
    rows = re.findall(r"^\|\s*`([a-z][\w-]*)`\s*\|\s*([^|]+?)\s*\|\s*([^|]*?)\s*\|\s*$", body, re.M)
    return {name: (tool, reason) for name, tool, reason in rows}


def all_strings(node):
    """Every object key and string value in a subtree."""
    if isinstance(node, dict):
        for key, value in node.items():
            yield key
            yield from all_strings(value)
    elif isinstance(node, list):
        for item in node:
            yield from all_strings(item)
    elif isinstance(node, str):
        yield node


def rule_positions(node):
    """Every string that occupies a rule-id position.

    Rule ids appear in exactly three places: the keys of a `rules` object, and the `rule`
    field of an `exceptions` or `findings` entry. Knowing the positions is what lets this
    check work without the validator knowing any tool's rule registry — the registries live
    in the tools, not in the spec.
    """
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "rules" and isinstance(value, dict):
                yield from value.keys()
            elif key in ("exceptions", "findings") and isinstance(value, list):
                for entry in value:
                    if isinstance(entry, dict) and isinstance(entry.get("rule"), str):
                        yield entry["rule"]
            yield from rule_positions(value)
    elif isinstance(node, list):
        for item in node:
            yield from rule_positions(item)


def vocabulary_nodes(case: dict):
    # Each subtree is handed over still wrapped in its own key, so `findings` at the top of a
    # case is recognised as a rule-id-bearing list the same way a nested one is.
    for key in VOCABULARY_SUBTREES:
        if key in case:
            yield {key: case[key]}


def check_bound_case(name: str, case: dict, placeholders, capabilities, tools, legacy_keys):
    """A `$any` case must carry no literal tool vocabulary at all."""
    used = set()
    for node in vocabulary_nodes(case):
        for text in all_strings(node):
            if text.startswith("$") and text not in CONFIG_DOLLAR_KEYS:
                if text not in placeholders:
                    fail(f"{name}: '{text}' is not a placeholder in the spec's §12 registry")
                used.add(text)
            elif text in tools:
                fail(
                    f"{name}: is '{ANY_TOOL}' but hardcodes the section key '{text}'; "
                    "use $tool or $alias"
                )
            elif text in legacy_keys:
                fail(
                    f"{name}: is '{ANY_TOOL}' but hardcodes the tool-owned legacy key "
                    f"'{text}'; use $foreignKey"
                )

        for rule in rule_positions(node):
            if rule not in placeholders:
                fail(
                    f"{name}: rule id '{rule}' is a literal; a '{ANY_TOOL}' case must name "
                    "rules with $rule1/$rule2/$foreignRule/$unknownRule"
                )

    requires = case.get("requires") or []
    if "$alias" in used and "alias" not in requires:
        fail(f"{name}: uses $alias but does not declare requires: [\"alias\"]")

    for capability in requires:
        if capability not in capabilities:
            fail(f"{name}: requires '{capability}', which is not in the spec's §12 registry")


def check_case_applicability(name: str, case: dict, capabilities, tools):
    for key, registry, where in (
        ("requires", capabilities, "spec's §12 capability registry"),
        ("appliesTo", tools, "spec's §3.3 tool registry"),
    ):
        if key not in case:
            continue
        value = case[key]
        if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
            fail(f"{name}: '{key}' must be an array of strings")
            continue
        for item in value:
            if item not in registry:
                fail(f"{name}: {key} names '{item}', which is not in the {where}")


def main() -> int:
    if not SPEC.exists():
        print(f"missing spec document: {SPEC}", file=sys.stderr)
        return 1

    spec_text = SPEC.read_text()
    errors, warnings, tools = parse_registries(spec_text)
    placeholders, capabilities = parse_binding_registries(spec_text)
    legacy_keys = parse_legacy_keys(spec_text)

    for name, values in (
        ("error", errors),
        ("warning", warnings),
        ("tool", tools),
        ("placeholder", placeholders),
        ("capability", capabilities),
        ("legacy-key", legacy_keys),
    ):
        if not values:
            fail(f"parsed no {name} registry from the spec — the document's shape changed")

    tool_specific = parse_tool_specific_table(CORPUS_README.read_text())

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
    bound = 0
    fixed: set[str] = set()

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

        if "description" in case and not str(case["description"]).strip():
            fail(f"{path.name}: description is empty")

        check_case_applicability(path.name, case, capabilities, tools)

        tool = case.get("tool")
        if tool == ANY_TOOL:
            bound += 1
            check_bound_case(
                path.name, case, placeholders, capabilities, tools, legacy_keys
            )
            if name in tool_specific:
                fail(
                    f"{path.name}: is '{ANY_TOOL}' but the README lists it as tool-specific"
                )
        elif tool and tool not in tools:
            fail(f"{path.name}: tool '{tool}' is not in the spec's §3.3 registry")
        elif tool:
            fixed.add(name)
            # A tool-specific case is a hole in cross-tool coverage. It is allowed, but it
            # has to be argued for in the README that adapter authors read.
            listed = tool_specific.get(name)
            if listed is None:
                fail(
                    f"{path.name}: is authored for '{tool}' but is not listed in the corpus "
                    "README's tool-specific table; make it '$any' or say why it cannot be"
                )
            else:
                if listed[0] != tool:
                    fail(
                        f"{path.name}: README's tool-specific table says '{listed[0]}', the "
                        f"case says '{tool}'"
                    )
                if not listed[1].strip():
                    fail(f"{path.name}: README's tool-specific table gives no reason")
            for node in vocabulary_nodes(case):
                for text in all_strings(node):
                    if text in placeholders:
                        fail(
                            f"{path.name}: is authored for '{tool}' but contains the "
                            f"placeholder '{text}'; nothing will bind it"
                        )

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

    for orphan in sorted(set(tool_specific) - fixed):
        fail(
            f"corpus README lists '{orphan}' as tool-specific, but no such tool-specific "
            "case exists"
        )

    # Everything under conformance/ is copied verbatim into six other repositories, at paths
    # that share no ancestry with this one. A relative link survives the copy as a dead link, so
    # vendored files must address this repository absolutely.
    for path in sorted((ROOT / "conformance").rglob("*.md")):
        for target in re.findall(r"\]\((\.{0,2}/[^)#]+)\)", path.read_text()):
            fail(
                f"{path.relative_to(ROOT)}: relative link '{target}' will not resolve once "
                "vendored; use the repository URL"
            )

    if problems:
        print(f"{len(problems)} problem(s):\n", file=sys.stderr)
        for problem in problems:
            print(f"  - {problem}", file=sys.stderr)
        return 1

    print(
        f"OK: {len(case_files)} cases ({bound} vocabulary-bound, {len(fixed)} tool-specific), "
        f"{len(tools)} tools, {len(placeholders)} placeholders, "
        f"{len(capabilities)} capabilities, {len(errors)} error codes, "
        f"{len(warnings)} warning codes."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
