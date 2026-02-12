# OpsFloor Deployment (Amsterdam VPS)

Goal: run OpsFloor as a single service that serves the UI + API + SSE reliably.

## Build (on VPS)

```bash
cd /opt/opsfloor/client
npm ci
npm run build

cd /opt/opsfloor/server
npm ci
# server will serve UI from ../client/dist by default
```

## Run (systemd)

Create unit:

```bash
sudo tee /etc/systemd/system/opsfloor.service >/dev/null <<'EOF'
[Unit]
Description=OpsFloor (Banana Bank Ops Floor)
After=network.target

[Service]
Type=simple
WorkingDirectory=/opt/opsfloor/server
Environment=PORT=8790
# optional: Environment=OPS_DB=/opt/opsfloor/data/opsfloor.db
# optional: Environment=UI_DIST=/opt/opsfloor/client/dist
ExecStart=/usr/bin/node /opt/opsfloor/server/src/index.js
Restart=always
RestartSec=2

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable --now opsfloor
sudo systemctl status opsfloor --no-pager
```

## Reverse proxy (recommended)

Use nginx to expose on 80/443 and keep 8789 private.

## Ports
- OpsFloor server default: 8790
- If using a cloud firewall: allow 80/443 (nginx) not 8789.
