#!/usr/bin/env bash
# Model-check backend/app/pipeline.py's session lifecycle with TLC (TLA+ tools v1.8.0).
# Usage: .agents/skills/verify-pipeline-formal/scripts/check.sh [cfg-name ...]   (default: all in checks/)
# Exit 0 only if every config produced its expected outcome (checks/expectations.tsv).
# Output: one line per config + TLC logs (with counterexample traces) in .verify/formal/<timestamp>/.
set -euo pipefail
SKILL="$(cd "$(dirname "$0")/.." && pwd)"
REPO="$(git -C "$SKILL" rev-parse --show-toplevel)"
TOOLS="${VERIFY_HOME:-$REPO/.verify}/tools"
JAR="$TOOLS/tla2tools-1.8.0.jar"
SHA=e1f11b75c4b5bc4478ba0ac5cb6ae28e40a01b0016bc33e0aa97da22dfdbcd7f
URL=https://github.com/tlaplus/tlaplus/releases/download/v1.8.0/tla2tools.jar

command -v java >/dev/null || { echo "BLOCKED: java not on PATH (TLC needs Java 11+)"; exit 2; }
if [ ! -f "$JAR" ]; then
  mkdir -p "$TOOLS"
  curl -fsSL -o "$JAR.part" "$URL" || { echo "BLOCKED: cannot download $URL"; exit 2; }
  mv "$JAR.part" "$JAR"
fi
echo "$SHA  $JAR" | sha256sum -c --quiet - || { echo "BLOCKED: $JAR checksum mismatch"; rm -f "$JAR"; exit 2; }

OUT="${VERIFY_HOME:-$REPO/.verify}/formal/$(date -u +%Y%m%dT%H%M%SZ)"
WORK="$(mktemp -d "${TMPDIR:-/tmp}/tlc.XXXXXX")"
trap 'rm -rf "$WORK"' EXIT
mkdir -p "$OUT"
cp "$SKILL/model/Pipeline.tla" "$WORK/"
names=("$@")
[ ${#names[@]} -eq 0 ] && names=($(cut -f1 "$SKILL/checks/expectations.tsv" | grep -v '^#'))

bad=0
for name in "${names[@]}"; do
  expect="$(awk -F'\t' -v n="$name" '$1==n {print $2}' "$SKILL/checks/expectations.tsv")"
  [ -n "$expect" ] || { echo "ERROR $name: no expectation in checks/expectations.tsv"; bad=1; continue; }
  cp "$SKILL/checks/$name.cfg" "$WORK/"
  log="$OUT/$name.log"
  # deadlock checking stays ON: the spec stutters only in Terminated, so a stuck state is reported
  (cd "$WORK" && timeout 600 java -XX:+UseParallelGC -cp "$JAR" tlc2.TLC -workers auto -cleanup \
      -config "$name.cfg" Pipeline.tla) > "$log" 2>&1 || true
  if grep -q "Model checking completed. No error has been found" "$log"; then
    got=pass
  elif inv="$(grep -oP 'Invariant \K\w+(?= is violated)' "$log" | head -1)" && [ -n "$inv" ]; then
    got="violation:$inv"
  elif grep -q "Deadlock reached" "$log"; then
    got=deadlock
  else
    got="error"
  fi
  states="$(grep -oP '\d+(?= distinct states found)' "$log" | tail -1 || true)"
  if [ "$got" = "$expect" ]; then
    echo "OK    $name: $got (expected) - ${states:-?} distinct states - $log"
  else
    echo "WRONG $name: got $got, expected $expect - $log"
    bad=1
  fi
done
echo "evidence: $OUT"
[ $bad -eq 0 ] && echo "FORMAL OK" || echo "FORMAL FAIL"
exit $bad
