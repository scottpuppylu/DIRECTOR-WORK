#!/bin/bash
# Outbound allowlist for the DW worker container.
#   DW_ALLOW_DOMAINS  space-separated host names allowed on TCP 443
#                     (run_worker.sh sets it; default api.anthropic.com)
# Allowed: loopback, replies to allowed connections, DNS to the resolvers in
# /etc/resolv.conf, TCP 443 to the IPv4 addresses the allowed names resolve
# to now. Everything else is rejected. IPv6 output is dropped.
# With --network none there is nothing to filter, so it only reports that.
set -euo pipefail
export PATH="/usr/sbin:/sbin:$PATH"   # iptables lives in /usr/sbin on Debian

ALLOW="${DW_ALLOW_DOMAINS:-api.anthropic.com}"

if [ -z "$(ls /sys/class/net 2>/dev/null | grep -v '^lo$' || true)" ]; then
  echo "firewall: no network interface besides lo; nothing to filter"
  exit 0
fi

iptables -F OUTPUT
iptables -P OUTPUT DROP
iptables -A OUTPUT -o lo -j ACCEPT
iptables -A OUTPUT -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT

for ns in $(awk '/^nameserver/ {print $2}' /etc/resolv.conf); do
  case "$ns" in
    *:*) continue ;;
  esac
  iptables -A OUTPUT -p udp -d "$ns" --dport 53 -j ACCEPT
  iptables -A OUTPUT -p tcp -d "$ns" --dport 53 -j ACCEPT
done

count=0
for name in $ALLOW; do
  for addr in $(getent ahostsv4 "$name" | awk '{print $1}' | sort -u); do
    iptables -A OUTPUT -p tcp -d "$addr" --dport 443 -j ACCEPT
    count=$((count + 1))
  done
done

iptables -A OUTPUT -j REJECT --reject-with icmp-port-unreachable

if command -v ip6tables >/dev/null 2>&1; then
  ip6tables -P OUTPUT DROP 2>/dev/null || true
  ip6tables -A OUTPUT -o lo -j ACCEPT 2>/dev/null || true
fi

echo "firewall: allow 443 to ${count} address(es) of: ${ALLOW}"
