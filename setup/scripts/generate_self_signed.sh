#!/usr/bin/env bash
set -euo pipefail

BASE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REPO_ROOT="$(dirname "${BASE_DIR}")"

# Load env
if [[ -f "${BASE_DIR}/.env" ]]; then
  set -o allexport
  source "${BASE_DIR}/.env"
  set +o allexport
fi

SERVER_IP="${SERVER_IP:-${1:-}}"
RUN_GROUP="${RUN_GROUP:-ubuntu}"

if [[ -z "${SERVER_IP}" ]]; then
  echo "ERROR: SERVER_IP not set. Set in setup/.env or pass as arg."
  exit 1
fi

echo "[SSL] generating self-signed cert for IP: ${SERVER_IP}"

sudo tee /etc/ssl/ip_san.cnf >/dev/null <<EOF
[req]
default_bits = 2048
prompt = no
default_md = sha256
x509_extensions = v3_req
distinguished_name = dn

[dn]
CN = ${SERVER_IP}

[v3_req]
subjectAltName = @alt_names

[alt_names]
IP.1 = ${SERVER_IP}
EOF

sudo openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
  -keyout /etc/ssl/private/sentinel.key \
  -out /etc/ssl/certs/sentinel.crt \
  -config /etc/ssl/ip_san.cnf

sudo chmod 600 /etc/ssl/private/sentinel.key

sudo install -d -m 750 -o root -g "${RUN_GROUP}" /etc/ssl/sentinel
sudo install -m 640 -o root -g "${RUN_GROUP}" /etc/ssl/certs/sentinel.crt  /etc/ssl/sentinel/fullchain.pem
sudo install -m 640 -o root -g "${RUN_GROUP}" /etc/ssl/private/sentinel.key /etc/ssl/sentinel/privkey.pem

echo "[SSL] done at /etc/ssl/sentinel/{fullchain.pem,privkey.pem}"
