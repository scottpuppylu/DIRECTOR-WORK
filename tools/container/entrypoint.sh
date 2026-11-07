#!/bin/bash
# Runs as root with only NET_ADMIN, NET_RAW, SETUID, SETGID and SETPCAP. Sets
# the firewall, starts the DNS allowlist resolver as user dwdns, then drops to
# user dw. Both run with no capabilities at all, so nothing started later can
# change the firewall, stop the resolver (another user) or get root back.
set -euo pipefail

/usr/local/bin/init_firewall.sh dns

if [ -n "$(ls /sys/class/net 2>/dev/null | grep -v '^lo$' || true)" ]; then
  setpriv --reuid=dwdns --regid=dwdns --clear-groups \
    --inh-caps=-all --ambient-caps=-all --bounding-set=-all \
    --no-new-privs -- /usr/local/bin/python3 -I -B /usr/local/bin/dns_allow.py --port 5353 &
  resolver=$! up=0
  for _ in $(seq 50); do
    # Without CAP_KILL root cannot signal dwdns (kill -0 fails), so look in /proc; a dead child is a zombie.
    grep -qs '^State:[[:space:]]*[^Z]' "/proc/$resolver/status" || break
    if (exec 3<>/dev/tcp/127.0.0.1/5353) 2>/dev/null; then up=1; break; fi
    sleep 0.1
  done
  [ "$up" = 1 ] || { echo "entrypoint: dns_allow.py did not start" >&2; exit 1; }
fi

/usr/local/bin/init_firewall.sh https

exec setpriv --reuid=dw --regid=dw --init-groups \
  --inh-caps=-all --ambient-caps=-all --bounding-set=-all \
  --no-new-privs -- "$@"
