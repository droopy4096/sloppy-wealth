#!/usr/bin/env bash
# Render every diagrams/*.mmd to diagrams/svg/*.svg using mermaid-cli.
# Needs Node.js. The first run downloads @mermaid-js/mermaid-cli and a headless Chromium.
# Keeps going after a failure and lists the failed files at the end.
set -uo pipefail
cd "$(dirname "$0")/.."
mkdir -p diagrams/svg
failed=()
for f in diagrams/*.mmd; do
  out="diagrams/svg/$(basename "${f%.mmd}").svg"
  echo "rendering $f -> $out"
  if ! npx -y @mermaid-js/mermaid-cli@11 -i "$f" -o "$out" -b white 2>&1 | grep -E '^(Error|Parse error|\.\.\.|-+\^|Expecting)' ; then :; fi
  [ -s "$out" ] && [ "$out" -nt "$f" ] || failed+=("$f")
done
if [ ${#failed[@]} -gt 0 ]; then
  echo "FAILED: ${failed[*]}"; exit 1
fi
echo "all diagrams rendered"
