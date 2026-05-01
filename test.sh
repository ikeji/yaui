#!/bin/sh

cat <<EOL
{"type":"dialog",
 "content": [
   {"type":"label", "text":"Hello World!!"}
 ]}
EOL

read f
echo $f
