#!/bin/bash
# launcher.sh - dmenu_path-style application launcher.
#
# Lists every executable on $PATH, filters as you type, and runs the
# selected one.  Activate by:
#   - Enter in the text box (runs the top match)
#   - Double-click / row-activate in the list
#   - Single click also selects, but doesn't launch
# Esc / window close exits without launching.
#
# Run with any of:
#   ./yaui-tui launcher.sh
#   ./yaui-gtk launcher.sh
#   ./yaui-web launcher.sh

# ---------------------------------------------------------------- helpers
extract() {
  python3 -c '
import sys, json
try:
    o = json.loads(sys.argv[2])
    v = o.get(sys.argv[1])
    if isinstance(v, bool): print("true" if v else "false")
    elif v is None: pass
    elif isinstance(v, dict):
        print(v.get("text", v.get("label", v.get("value", ""))))
    else: print(v)
except Exception: pass
' "$1" "$2"
}

# Build a JSON array literal from one-binary-per-line stdin (max N entries).
to_json_array() {
  python3 -c '
import sys, json
items = [l.rstrip() for l in sys.stdin if l.strip()]
print(json.dumps(items[:int(sys.argv[1])]))
' "$1"
}

# JSON-escape a shell string (no surrounding quotes).
json_body() {
  python3 -c 'import sys, json; sys.stdout.write(json.dumps(sys.argv[1])[1:-1])' "$1"
}

# ---------------------------------------------------------------- index
# Enumerate executables in $PATH once at startup.
build_index() {
  IFS=':' read -ra dirs <<<"$PATH"
  for d in "${dirs[@]}"; do
    [ -z "$d" ] && continue
    [ -d "$d" ] || continue
    for f in "$d"/*; do
      [ -x "$f" ] && [ -f "$f" ] && printf '%s\n' "${f##*/}"
    done
  done | sort -u
}

INDEX_FILE=$(mktemp)
trap 'rm -f "$INDEX_FILE"' EXIT
build_index > "$INDEX_FILE"
TOTAL=$(wc -l < "$INDEX_FILE" | tr -d ' ')

# ---------------------------------------------------------------- state
query=""
matches_count=0
top=""

# ---------------------------------------------------------------- emit
emit_ui() {
  local q_j items_json
  q_j=$(json_body "$query")
  if [ -z "$query" ]; then
    items_json=$(head -200 "$INDEX_FILE" | to_json_array 200)
    matches_count=$TOTAL
    top=$(head -1 "$INDEX_FILE")
  else
    items_json=$(grep -i -- "$query" "$INDEX_FILE" | head -200 | to_json_array 200)
    matches_count=$(grep -ic -- "$query" "$INDEX_FILE")
    top=$(grep -i -- "$query" "$INDEX_FILE" | head -1)
  fi
  cat <<EOL
{"type":"dialog","title":"launcher",
 "content":[{"type":"vbox","children":[
  {"type":"hbox","children":[
    {"type":"label","text":"Run:"},
    {"type":"textbox","id":"q","width":32,"value":"$q_j"}
  ]},
  {"type":"label","text":"$matches_count match(es) of $TOTAL — Enter runs top, double-click runs item"},
  {"type":"list","id":"results","height":12,"items":$items_json}
 ]}]}
EOL
}

# ---------------------------------------------------------------- actions
launch() {
  local cmd=$1
  [ -z "$cmd" ] && return
  # Detach so the launcher can exit cleanly.
  setsid "$cmd" </dev/null >/dev/null 2>&1 &
  disown 2>/dev/null || true
  exit 0
}

# ---------------------------------------------------------------- loop
emit_ui

while IFS= read -r line; do
  t=$(extract type "$line")
  id=$(extract id "$line")
  case "$t" in
    close) exit 0 ;;
    change)
      case "$id" in
        q)
          new=$(extract value "$line")
          # Re-render only when the query actually changed.
          if [ "$new" != "$query" ]; then
            query=$new
            emit_ui
          fi
          ;;
        # (Single click in the list just sets selection — no action.)
      esac ;;
    submit)
      if [ "$id" = q ]; then
        # Enter in the textbox: run the top match (if any).
        [ -n "$top" ] && launch "$top"
      fi ;;
    select)
      if [ "$id" = results ]; then
        item=$(extract item "$line")
        [ -n "$item" ] && launch "$item"
      fi ;;
  esac
done
