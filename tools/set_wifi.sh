#!/bin/bash
# Writes firmware/main/secrets.h: the Wi-Fi networks the tutor may use (home, phone hotspot...) and the
# OpenRouter key from .env. Passwords are typed here, never shown or sent anywhere else.
# Then rebuild + flash:  source ~/esp/esp-idf/export.sh && cd firmware && idf.py -p /dev/cu.usbmodem101 flash
set -e
cd "$(dirname "$0")/.."
key=$(grep '^OPENROUTER_API_KEY=' .env | cut -d= -f2- | tr -d '"'"'")
[ -n "$key" ] || { echo "No OPENROUTER_API_KEY in .env"; exit 1; }
esc() { printf '%s' "$1" | sed 's/\\/\\\\/g; s/"/\\"/g'; }
nets=""
echo "Add each Wi-Fi network the tutor may use (home, your phone's hotspot...). Names are case-sensitive."
while true; do
  read -r -p "Wi-Fi name (blank when done): " ssid
  [ -z "$ssid" ] && break
  read -r -s -p "Password for $ssid: " pass; echo
  nets+="{\"$(esc "$ssid")\", \"$(esc "$pass")\"}, "
done
[ -n "$nets" ] || { echo "No networks entered; secrets.h unchanged."; exit 1; }
cat > firmware/main/secrets.h <<EOF
// Local secrets (gitignored). Written by tools/set_wifi.sh.
#pragma once
#define WIFI_NETWORKS { ${nets%, } }
#define OPENROUTER_API_KEY "$key"
EOF
echo "Saved firmware/main/secrets.h ($(grep -o '{"' firmware/main/secrets.h | wc -l | tr -d ' ') networks)"
