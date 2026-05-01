#!/bin/bash
# monitor.sh - system monitor demo for yauitoolkit.
# Works with all three runtimes:
#   ./yaui-tui monitor.sh
#   ./yaui-gtk monitor.sh
#   ./yaui-web monitor.sh

prev_total=0
prev_idle=0

# Sets cpu_pct from two snapshots of /proc/stat.
cpu_sample() {
  local user nice system idle iowait irq softirq steal _rest
  read -r _rest user nice system idle iowait irq softirq steal _rest < /proc/stat
  local total=$((user + nice + system + idle + iowait + irq + softirq + steal))
  local idle_t=$((idle + iowait))
  if [ "$prev_total" -gt 0 ] && [ "$total" -gt "$prev_total" ]; then
    local dt=$((total - prev_total))
    local di=$((idle_t - prev_idle))
    cpu_pct=$(( (dt - di) * 100 / dt ))
  else
    cpu_pct=0
  fi
  prev_total=$total
  prev_idle=$idle_t
}

# Sets mem_pct, mem_used_gib, mem_total_gib from /proc/meminfo.
mem_sample() {
  local mt ma
  mt=$(awk '/^MemTotal:/     {print $2; exit}' /proc/meminfo)
  ma=$(awk '/^MemAvailable:/ {print $2; exit}' /proc/meminfo)
  mem_pct=$(( (mt - ma) * 100 / mt ))
  mem_total_gib=$(awk -v t="$mt"        'BEGIN{printf "%.1f", t/1048576}')
  mem_used_gib=$( awk -v t="$mt" -v a="$ma" 'BEGIN{printf "%.1f", (t-a)/1048576}')
}

# Sets disk_pct, disk_used_gib, disk_total_gib for the root filesystem.
disk_sample() {
  local size used pcent line
  line=$(df -P / | tail -1)
  size=$(echo  "$line" | awk '{print $2}')
  used=$(echo  "$line" | awk '{print $3}')
  pcent=$(echo "$line" | awk '{print $5}')
  disk_pct=${pcent%\%}
  disk_total_gib=$(awk -v s="$size" 'BEGIN{printf "%.1f", s/1048576}')
  disk_used_gib=$( awk -v u="$used" 'BEGIN{printf "%.1f", u/1048576}')
}

emit_ui() {
  local now
  now=$(date '+%Y-%m-%d %H:%M:%S')
  cat <<EOL
{"type":"dialog","title":"System Monitor",
 "content":[{"type":"vbox","children":[
   {"type":"label","text":"Time:  $now","bold":true},
   {"type":"label","text":""},
   {"type":"label","text":"CPU    ${cpu_pct}%"},
   {"type":"progressbar","value":$cpu_pct,"max":100,"width":40,"show_text":true},
   {"type":"label","text":""},
   {"type":"label","text":"Memory ${mem_used_gib} / ${mem_total_gib} GiB  (${mem_pct}%)"},
   {"type":"progressbar","value":$mem_pct,"max":100,"width":40,"show_text":true},
   {"type":"label","text":""},
   {"type":"label","text":"Disk   ${disk_used_gib} / ${disk_total_gib} GiB  (${disk_pct}%)  on /"},
   {"type":"progressbar","value":$disk_pct,"max":100,"width":40,"show_text":true},
   {"type":"label","text":""},
   {"type":"hbox","children":[
     {"type":"button","id":"quit","text":"Quit"}
   ]}
 ]}]}
EOL
}

# Seed CPU history so the first displayed value is meaningful.
cpu_sample
sleep 0.2
cpu_sample

while :; do
  cpu_sample
  mem_sample
  disk_sample
  emit_ui
  # Wait up to 1s for an event from the runtime. If the user closes the
  # window or clicks Quit, exit cleanly.
  if read -r -t 1 line; then
    case "$line" in
      *'"close"'*|*'"quit"'*) exit 0 ;;
    esac
  fi
done
