# DW worker image (1.2.0). Build inside WSL:
#   docker build -t dw-worker:1.2.0 tools/container
# The base image is pinned by digest and Claude Code by version. To upgrade,
# change both lines below and build again; nothing updates by itself.
# linux/amd64 manifest of python:3.12-slim-bookworm (3.12.16), checked 2026-11-07.
FROM python:3.12-slim-bookworm@sha256:0f086103b026048cc50cb5da25ec435c023c5241a83fc44daea593377abc61c4

ARG CLAUDE_VERSION=2.1.317

RUN apt-get update \
 && apt-get install -y --no-install-recommends git iptables ca-certificates curl \
 && rm -rf /var/lib/apt/lists/* \
 && git config --system safe.directory '*' \
 && git config --system core.filemode false \
 && useradd --create-home --uid 1000 --shell /bin/bash dw

USER dw
RUN curl -fsSL https://claude.ai/install.sh | bash -s "${CLAUDE_VERSION}" \
 && /home/dw/.local/bin/claude --version | grep -F "${CLAUDE_VERSION}"

USER root
COPY entrypoint.sh init_firewall.sh dns_allow.py /usr/local/bin/
# dwdns runs dns_allow.py: the only user the firewall lets reach the upstream resolvers.
# Kept after the layers above, so adding it did not rebuild them.
RUN chmod 755 /usr/local/bin/entrypoint.sh /usr/local/bin/init_firewall.sh /usr/local/bin/dns_allow.py \
 && useradd --system --uid 999 --no-create-home --shell /usr/sbin/nologin dwdns
ENV PATH=/home/dw/.local/bin:/usr/local/bin:/usr/bin:/bin \
    HOME=/home/dw \
    CLAUDE_CONFIG_DIR=/home/dw/.claude \
    DISABLE_AUTOUPDATER=1
WORKDIR /work
ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
CMD ["bash"]
