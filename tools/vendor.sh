#!/bin/bash
# Vendor the conformance corpus into a consuming tool repository.
#
# Copies conformance/dependably/ from a pinned commit of this repository and writes a
# VENDOR.md beside it recording exactly what was copied. The recorded commit is the point:
# a tool sitting on an older corpus is not broken, it is testing an older contract — but
# only if you can tell, which is what the drift between copies cost before.
#
# Usage, from the consuming repository's root:
#   tools/vendor.sh <destination-dir> [ref]
#
#   tools/vendor.sh tests/Dependably.PdbCheck.Tests/conformance
#   tools/vendor.sh tests/conformance v1.2.0

set -euo pipefail

SPEC_REPO="${DEPENDABLY_SPEC_REPO:-https://gitlab.northwardlabs.ca/moonlitlabs/dependably-spec.git}"
DEST="${1:-}"
REF="${2:-main}"

if [ -z "$DEST" ]; then
  echo "usage: vendor.sh <destination-dir> [ref]" >&2
  exit 2
fi

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

echo "Fetching $SPEC_REPO @ $REF ..."
git clone --quiet --depth 1 --branch "$REF" "$SPEC_REPO" "$WORK/spec" 2>/dev/null \
  || git clone --quiet "$SPEC_REPO" "$WORK/spec"
git -C "$WORK/spec" checkout --quiet "$REF"

SHA="$(git -C "$WORK/spec" rev-parse HEAD)"
DATE="$(git -C "$WORK/spec" log -1 --format=%cI)"

mkdir -p "$DEST"
# Replace rather than merge: a case deleted upstream must disappear here too, or the copy
# quietly keeps testing a contract that no longer exists.
rm -rf "${DEST:?}/dependably"
cp -R "$WORK/spec/conformance/dependably" "$DEST/dependably"

# Record a checksum for every vendored file. Verification then needs no network access and
# no credentials, which matters because the consuming repositories run CI on two different
# forges and one of them cannot reach this one at all. It also makes the check fast enough to
# run on every pipeline rather than being something people skip.
(
  cd "$DEST/dependably" && find . -type f | LC_ALL=C sort | while IFS= read -r f; do
    printf '%s  %s\n' "$(shasum -a 256 "$f" 2>/dev/null | cut -d' ' -f1 || sha256sum "$f" | cut -d' ' -f1)" "${f#./}"
  done
) > "$DEST/corpus.sha256"

cat > "$DEST/VENDOR.md" <<EOF
# Vendored conformance corpus

Copied from the Dependably spec repository. Do not edit these files here — a change made in
this copy is invisible to every other tool and will be overwritten by the next sync. Change
the spec repository instead, then re-run the sync.

| | |
|---|---|
| Source | $SPEC_REPO |
| Ref | \`$REF\` |
| Commit | \`$SHA\` |
| Committed | $DATE |

Re-sync with:

\`\`\`bash
git clone --depth 1 $SPEC_REPO /tmp/dependably-spec
/tmp/dependably-spec/tools/vendor.sh $DEST $REF
\`\`\`

\`corpus.sha256\` beside this file records a checksum for every vendored file, written at
copy time. CI verifies the copy against it without needing to reach this repository, so drift
is caught on every pipeline rather than only when someone thinks to look.

A newer upstream commit is not automatically a problem: this copy pins the contract version
this tool is tested against. Update deliberately, and re-run the tool's test suite.
EOF

echo "Vendored $(find "$DEST/dependably/cases" -name '*.json' | wc -l | tr -d ' ') cases into $DEST/dependably"
echo "Recorded $SHA in $DEST/VENDOR.md"
