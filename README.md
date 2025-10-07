# SentinelSever_AI
ㅇㅇ

### Setup
```
# 1) 서버에서 레포 클론
git clone https://github.com/BoB-Sentinel-Solution/SentinelServer_AI.git
cd SentinelServer_AI

# 2) 환경파일 준비 (선택)
cp setup/.env.example setup/.env
nano setup/.env   # SERVER_IP, APP_DST, RUN_USER 필요 시 수정

# 3) 한 번에 배포
bash setup/scripts/deploy.sh
 ```

### Delete
```
# 1) 기본(확인 후 진행)
cd ~/SentinelServer_AI/uninstall
sudo bash uninstall.sh

# 2) 무확인 전체 제거(서비스/코드/venv/DB/인증서)
sudo bash uninstall.sh --force

# 3) DB는 남기고 나머지만 제거
sudo bash uninstall.sh --force --keep-db

# 4) 서비스만 제거(코드/DB/파일은 유지)
sudo bash uninstall.sh --only-service
```
