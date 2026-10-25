// Copy to secrets.h (gitignored), or run tools/set_wifi.sh to write it.
#pragma once
// Every network the tutor may use; it joins whichever is strongest in range.
#define WIFI_NETWORKS { {"home-wifi", "password"}, {"my-phone", "hotspot-password"} }
// From https://openrouter.ai/keys: speech-to-text, Claude and the voice all go through it.
#define OPENROUTER_API_KEY "sk-or-..."
