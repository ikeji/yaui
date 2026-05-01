#!/bin/sh
# Interactive sample: a small form with a textbox, a checkbox, and two buttons.
# Run with:  ./yaui-tui sample.sh

emit_form() {
  cat <<EOL
{"type":"dialog","title":"yaui sample",
 "content":[
  {"type":"vbox","children":[
    {"type":"label","text":"Name:"},
    {"type":"textbox","id":"name","width":24},
    {"type":"checkbox","id":"newsletter","text":"Subscribe to newsletter"},
    {"type":"label","text":""},
    {"type":"hbox","children":[
      {"type":"button","id":"ok","text":"OK"},
      {"type":"button","id":"cancel","text":"Cancel"}
    ]}
  ]}
 ]}
EOL
}

emit_done() {
  cat <<EOL
{"type":"dialog","title":"Thanks","content":[
  {"type":"vbox","children":[
    {"type":"label","text":"Form submitted."},
    {"type":"label","text":"Press Esc to close."}
  ]}
]}
EOL
}

emit_form

while IFS= read -r line; do
  case "$line" in
    *'"id": "ok"'*|*'"id":"ok"'*)
      emit_done
      ;;
    *'"id": "cancel"'*|*'"id":"cancel"'*)
      break
      ;;
    *'"type": "close"'*|*'"type":"close"'*)
      break
      ;;
  esac
done
