#!/usr/bin/env bash
set -euo pipefail

echo "[UFW] installing & configuring..."
sudo apt-get update -y
sudo apt-get install -y ufw

sudo ufw allow OpenSSH
sudo ufw allow 80/tcp || true
sudo ufw allow 443/tcp
yes | sudo ufw enable || true

echo "[UFW] status:"
sudo ufw status verbose || true
