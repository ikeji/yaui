#!/bin/bash
# showcase.sh - exercises every widget supported by yaui.
# Run with any of:
#   ./yaui-tui showcase.sh
#   ./yaui-gtk showcase.sh
#   ./yaui-web showcase.sh

clicks=0
name=""
notes=""
subscribed=false
fruit="apple"
progress=50
last="(none)"

# Extract a top-level JSON field from a single-line event using Python.
# Usage:  VAR=$(extract <field> <line>)
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

# Encode an arbitrary shell string as the body of a JSON string literal
# (no surrounding quotes, with all required escaping).
json_body() {
  python3 -c 'import sys, json; sys.stdout.write(json.dumps(sys.argv[1])[1:-1])' "$1"
}

emit_ui() {
  local checked
  [ "$subscribed" = "true" ] && checked=true || checked=false
  local nj notes_j last_j
  nj=$(json_body "$name")
  notes_j=$(json_body "$notes")
  last_j=$(json_body "$last")
  cat <<EOL
{"type":"dialog","title":"yaui showcase",
 "content":[{"type":"hbox","children":[
   {"type":"vbox","children":[
     {"type":"label","text":"Labels","bold":true},
     {"type":"label","text":"plain text"},
     {"type":"label","text":"bold text","bold":true},
     {"type":"label","text":""},

     {"type":"label","text":"Buttons","bold":true},
     {"type":"hbox","children":[
       {"type":"button","id":"inc","text":"+1"},
       {"type":"button","id":"reset","text":"Reset"}
     ]},
     {"type":"label","text":"clicks: $clicks"},
     {"type":"label","text":""},

     {"type":"label","text":"Textbox (Enter to apply)","bold":true},
     {"type":"textbox","id":"name","width":18,"value":"$nj"},
     {"type":"label","text":"hello, $name"},
     {"type":"label","text":""},

     {"type":"label","text":"Checkbox","bold":true},
     {"type":"checkbox","id":"sub","text":"Subscribe","checked":$checked},
     {"type":"label","text":"subscribed = $subscribed"}
   ]},
   {"type":"vbox","children":[
     {"type":"label","text":"List","bold":true},
     {"type":"list","id":"fruit","height":3,"items":["apple","banana","cherry","durian"]},
     {"type":"label","text":"selected: $fruit"},
     {"type":"label","text":""},

     {"type":"label","text":"Textarea","bold":true},
     {"type":"textarea","id":"notes","width":24,"height":3,"value":"$notes_j"},
     {"type":"label","text":""},

     {"type":"label","text":"Progressbar","bold":true},
     {"type":"progressbar","value":$progress,"max":100,"width":24,"show_text":true},
     {"type":"hbox","children":[
       {"type":"button","id":"pm","text":"-10"},
       {"type":"button","id":"pp","text":"+10"}
     ]},
     {"type":"label","text":"$progress%"},
     {"type":"label","text":""},

     {"type":"label","text":"Last event","bold":true},
     {"type":"label","text":"$last_j"}
   ]}
 ]}]}
EOL
}

emit_ui

while IFS= read -r line; do
  t=$(extract type "$line")
  id=$(extract id "$line")
  case "$t" in
    close) exit 0 ;;

    click)
      case "$id" in
        inc)   clicks=$((clicks + 1)); last="click +1";    emit_ui ;;
        reset) clicks=0;               last="click Reset"; emit_ui ;;
        pp)    progress=$((progress + 10)); [ $progress -gt 100 ] && progress=100
               last="+10 → $progress%"; emit_ui ;;
        pm)    progress=$((progress - 10)); [ $progress -lt 0 ]   && progress=0
               last="-10 → $progress%"; emit_ui ;;
      esac
      ;;

    submit)
      if [ "$id" = name ]; then
        name=$(extract value "$line")
        last="submit name=\"$name\""
        emit_ui
      fi
      ;;

    change)
      case "$id" in
        # textbox/textarea: capture state but DON'T re-render. Re-rendering
        # on every keystroke would reset the cursor in GTK/Web.
        name)  name=$(extract value "$line") ;;
        notes) notes=$(extract value "$line") ;;
        sub)
          subscribed=$(extract value "$line")
          last="checkbox=$subscribed"
          emit_ui
          ;;
        fruit)
          v=$(extract item "$line")
          [ -z "$v" ] && v=$(extract value "$line")
          fruit="$v"
          last="list select=$fruit"
          emit_ui
          ;;
      esac
      ;;

    select)
      if [ "$id" = fruit ]; then
        v=$(extract item "$line")
        [ -n "$v" ] && fruit="$v"
        last="list activate=$fruit"
        emit_ui
      fi
      ;;
  esac
done
