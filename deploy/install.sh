#!/bin/bash
set -euo pipefail
test "$(hostname)" = xingbox
command -v python3
command -v openssl
install -d -m 700 /root/maintenance/pulse-20261014
cp -a /etc/nftables.conf /root/maintenance/pulse-20261014/nftables.before
getent passwd pulse >/dev/null || useradd --system --home-dir /var/lib/pulse --shell /usr/sbin/nologin pulse
install -d -m 755 /home/fanxing/services/pulse
tar -xzf /tmp/pulse-release.tgz -C /home/fanxing/services/pulse
chown -R root:root /home/fanxing/services/pulse
install -d -m 750 -o root -g pulse /etc/pulse
install -m 640 -o root -g pulse /tmp/pulse-config.json /etc/pulse/config.json
if [ ! -f /etc/pulse/tls.key ]; then
  openssl req -x509 -newkey rsa:2048 -nodes -days 365 \
    -keyout /etc/pulse/tls.key -out /etc/pulse/tls.crt \
    -subj '/CN=bh.xingbox.me' \
    -addext 'subjectAltName=DNS:bh.xingbox.me,IP:23.246.165.183,IP:2602:faa8:8:b5::a'
fi
chown root:pulse /etc/pulse/tls.key /etc/pulse/tls.crt
chmod 640 /etc/pulse/tls.key
chmod 644 /etc/pulse/tls.crt
install -m 644 /home/fanxing/services/pulse/deploy/pulse.service /etc/systemd/system/pulse.service
python3 - <<'PY'
from pathlib import Path
p=Path('/etc/nftables.conf')
s=p.read_text()
rule='        tcp dport { 80, 443 } ct state new counter accept comment "Pulse website"\n'
anchor='        tcp dport 22 ct state new counter accept comment "SSH public-key access"\n'
if 'comment "Pulse website"' not in s:
    if anchor not in s:raise SystemExit('Cannot find SSH firewall anchor; no changes made')
    s=s.replace(anchor,anchor+rule)
    p.write_text(s)
PY
nft -c -f /etc/nftables.conf
nft -f /etc/nftables.conf
systemctl daemon-reload
systemctl enable --now pulse.service
rm -f -- /tmp/pulse-config.json /tmp/pulse-release.tgz
systemctl is-active pulse.service
ss -lntp
