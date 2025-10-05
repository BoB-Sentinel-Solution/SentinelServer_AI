# SentinelSever_AI
ㅇㅇ

```
# 1) 서버에서 레포 클론
git clone https://github.com/BoB-Sentinel-Solution/SentinelServer_AI.git
cd SentinelServer_AI

# 2) 환경파일 준비
cp setup/.env.example setup/.env
nano setup/.env   # SERVER_IP, APP_DST, RUN_USER 필요 시 수정

# 3) 한 번에 배포
bash setup/scripts/deploy.sh

# 4) 상태/로그/헬스
systemctl status sentinel
journalctl -u sentinel -f
curl -k https://<SERVER_IP>/healthz
 ```
