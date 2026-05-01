#!/bin/bash
# counter.sh - interactive counter demo for yauitoolkit.
# Run with any of:
#   ./yaui-tui counter.sh
#   ./yaui-gtk counter.sh
#   ./yaui-web counter.sh

count=0

emit_ui() {
  cat <<EOL
{"type":"dialog","title":"Counter",
 "content":[{"type":"vbox","children":[
   {"type":"label","text":"Count: $count","bold":true},
   {"type":"hbox","children":[
     {"type":"button","id":"inc","text":"+1"},
     {"type":"button","id":"reset","text":"Reset"}
   ]}
 ]}]}
EOL
}

emit_ui
while IFS= read -r line; do
  case "$line" in
    *'"close"'*)  exit 0 ;;
    *'"inc"'*)    count=$((count + 1)); emit_ui ;;
    *'"reset"'*)  count=0;               emit_ui ;;
  esac
done
