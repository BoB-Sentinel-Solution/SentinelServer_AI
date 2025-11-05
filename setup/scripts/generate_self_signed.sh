#!/usr/bin/env bash
set -euo pipefail

# 위치: ~/SentinelServer_AI/setup/scripts/generate_self_signed.sh

BASE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${BASE_DIR}/.env"

if [[ -f "${ENV_FILE}" ]]; then
  set -o allexport; source "${ENV_FILE}"; set +o allexport
fi

DOMAIN="${DOMAIN:-bobsentinel.com}"
SERVER_IP="${SERVER_IP:-$(curl -s https://ifconfig.me || echo 127.0.0.1)}"

CERT_DIR="/etc/ssl/sentinel"
mkdir -p "${CERT_DIR}"

cat > "${CERT_DIR}/openssl.cnf" <<EOF
[req]
distinguished_name = req_distinguished_name
x509_extensions = v3_req
prompt = no

[req_distinguished_name]
C = KR
ST = Seoul
L = Seoul
O = Sentinel
OU = Server
CN = ${DOMAIN}

[v3_req]
keyUsage = critical, digitalSignature, keyEncipherment
extendedKeyUsage = serverAuth
subjectAltName = @alt_names

[alt_names]
DNS.1 = ${DOMAIN}
DNS.2 = www.${DOMAIN}
IP.1 = ${SERVER_IP}
EOF

openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
  -keyout "${CERT_DIR}/privkey.pem" \
  -out "${CERT_DIR}/fullchain.pem" \
  -config "${CERT_DIR}/openssl.cnf"

chmod 600 "${CERT_DIR}/privkey.pem"
echo "[SELF] generated self-signed certificate at ${CERT_DIR}"
