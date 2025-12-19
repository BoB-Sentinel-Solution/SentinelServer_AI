# SentinelServer_AI

Sentinel Solution의 **서버 레포지토리**입니다.  
에이전트(설치형/브라우저 확장 등)에서 전달되는 **프롬프트/파일/메타데이터 로그를 수집**하고, 중요정보를 정규표현식 및 로컬LLM을 사용하여 탐지합니다.<br>
설정한 서버 내부 정책으로 대응하며 분석 결과를 저장/시각화하기 위한 API 및 대시보드를 제공합니다.

---

## What’s in this repo

- **FastAPI 기반 서버 애플리케이션**
- **Dashboard(Web UI)** 정적 리소스 제공
- **서비스 배포 자동화 스크립트**(venv/DB/서비스/인증서 등 포함)
- **삭제(uninstall) 자동화 스크립트** 제공

---

## Repository Structure (High-level)

레포 루트에 다음 디렉터리/파일들이 포함됩니다.

- `app.py` : FastAPI 앱 엔트리 포인트
- `config.py` : 서버 설정 로딩/환경변수
- `db.py` : DB 연결/세션/초기화
- `models.py` : DB 모델(SQLAlchemy)
- `schemas.py` : API 스키마(Pydantic)
- `routers/` : API 라우터 모음
- `services/` : 핵심 비즈니스 로직(분석/저장/처리 등)
- `utils/` : 유틸 모듈
- `dashboard/` : 대시보드 정적 파일(HTML/CSS/JS)
- `setup/` : 배포 스크립트 및 환경파일 템플릿
- `uninstall/` : 제거 스크립트
- `requirements.txt` : 파이썬 의존성 목록

---

## Setup
> 운영 배포는 **Setup 섹션의 deploy 스크립트 사용을 권장**합니다.

```bash
# 1) 서버에서 레포 클론
git clone https://github.com/BoB-Sentinel-Solution/SentinelServer_AI.git
cd SentinelServer_AI

# 2) 환경파일 준비 (선택)
nano setup/.env   # SERVER_IP, APP_DST, RUN_USER 필요 시 수정

# 3) 한 번에 배포(서비스/코드/venv/DB/인증서)
bash setup/scripts/deploy.sh
```

## 주요 변수 (`setup/.env`)
배포 환경변수는 `setup/.env`를 환경에 맞게 수정합니다.

### SERVER_IP
서버 IP 또는 도메인(외부 접속 주소)입니다.  
대시보드/API 접근 및 인증서 설정 등에 사용됩니다.

### APP_DST
설치 경로(배포 위치)입니다.  
서버 코드가 배치될 디렉터리 경로를 의미합니다.

### RUN_USER
서비스 실행 유저입니다.  
systemd 서비스가 해당 계정 권한으로 실행됩니다.

> 전체 키 목록 및 상세 의미는 **`setup/.env`**를 기준으로 확인하세요.


---

## Uninstall / Delete

레포에 포함된 `uninstall/uninstall.sh` 스크립트로 상태별 제거 옵션을 지원합니다.

```bash
# 1) 기본(확인 후 진행)
cd ~/SentinelServer_AI/uninstall
sudo bash uninstall.sh

# 2) 무확인 전체 제거(서비스/코드/venv/DB/인증서)
sudo bash uninstall.sh --force

# 4=3) 서비스만 제거(코드/DB/파일은 유지)
sudo bash uninstall.sh --only-service
```

> 운영 환경에서는 DB 보존 여부를 먼저 결정한 뒤 실행하는 것을 권장합니다.

## API & Dashboard

- API 라우팅은 `routers/` 디렉터리에서 관리합니다.
- 대시보드는 `dashboard/` 정적 리소스 기반으로 제공됩니다.

실제 엔드포인트 목록 및 요청/응답 스키마는 `routers/`, **`schemas.py`**를 기준으로 문서화하는 것을 권장합니다.


---

## Operational Notes

- 운영 환경에서는 `setup/scripts/deploy.sh` 기반 배포를 권장합니다.
- 본 레포는 인증서/서비스/DB를 포함한 '원클릭 배포'를 전제로 구성되어 있습니다.
- 내부망/외부망 환경을 분리 운영하는 경우, 환경별로 `setup/.env` 값을 분리(예: 내부용/외부용)하여 관리하는 것을 추천합니다.

---

## License

Apache-2.0


