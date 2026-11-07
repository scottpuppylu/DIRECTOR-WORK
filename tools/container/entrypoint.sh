#!/bin/bash
# Runs as root with only NET_ADMIN, NET_RAW, SETUID and SETGID. Sets the
# firewall, then drops to user dw with no capabilities at all, so nothing
# started later can change the firewall or get root back.
set -euo pipefail

/usr/local/bin/init_firewall.sh

exec setpriv --reuid=dw --regid=dw --init-groups \
  --inh-caps=-all --ambient-caps=-all --bounding-set=-all \
  --no-new-privs -- "$@"
