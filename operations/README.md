# KSC 2026 접속·운영 자동화

이 폴더는 KSC 2026 GH200 × PhysicsNeMo 실습에서 사용하는 공용 Slurm·Jupyter 실행 경로와 중앙 배포 도구를 관리합니다.

행사 사용자는 모두 같은 명령을 실행합니다.

```bash
/scratch/hackathon/ksc2026/bin/ksc2026
```

별도 계정 분류나 고정 계산 노드표는 사용하지 않습니다. 유효한 KISTI PILOT 계정으로 로그인한 사용자는 Slurm `gpu` 파티션에 NVIDIA GH200 한 개를 요청하며, Slurm이 요청 시점에 사용할 수 있는 계산 노드를 동적으로 배정합니다.

## 사용자 동선

```text
로컬 터미널 1
  └─ 일반 SSH → KISTI PILOT 로그인 노드
       └─ /scratch/hackathon/ksc2026/bin/ksc2026
            └─ Slurm gpu 파티션에 GH200 1개 요청
                 └─ 동적으로 배정된 계산 노드에서 중앙 SIF로 JupyterLab 실행

런처 화면
  ├─ 배정 계산 노드·물리 GPU 번호
  ├─ 완성된 ssh -N -L 명령
  └─ token이 포함된 JupyterLab 주소

로컬 터미널 2
  └─ 출력된 ssh -N -L 명령을 그대로 실행해 터널 유지

웹 브라우저
  └─ http://127.0.0.1:8888/... → SSH 터널 → 계산 노드 JupyterLab
```

사용자는 계산 노드, 포트, 계정 또는 로그인 호스트를 직접 채우지 않습니다. 공용 런처가 Slurm의 실제 배정 결과를 확인한 뒤 완성된 SSH 명령을 한 줄로 출력합니다. `ssh -N`은 터널만 유지하므로 인증 뒤에 터미널 프롬프트가 나타나지 않는 것이 정상입니다.

## 확정한 실행 계약

- Slurm 파티션: `gpu`
- GPU 요청: `gpu:nvidia_gh200_120gb:1`
- 노드 선택: `--nodelist`와 `--exclude` 없이 Slurm에 위임
- 세션 시간: 최대 24시간
- 계산 노드 Jupyter: 내부 인터페이스 `0.0.0.0:<동적 원격 포트>`
- 사용자 PC 로컬 포트: 기본 `127.0.0.1:8888`
- 인증: 48자리 16진수 Jupyter token과 OpenSSH OTP·비밀번호
- 실행 이미지: `/scratch/hackathon/ksc2026/images/`의 검증된 ARM64 SIF 한 벌
- 강의자료: 검증된 GitHub commit별 읽기 전용 중앙 release
- 개인 상태: `/scratch/$USER/ksc2026/{session,workspaces,logs}`

Slurm과 cgroup이 각 Job에 GH200 한 개만 보이도록 격리합니다. 성공 화면의 물리 GPU 번호는 고정 좌석이나 포트에서 추정하지 않고 실제 Slurm·계산 런타임 결과에서 읽습니다. 컨테이너 안에서는 배정된 장치가 `cuda:0`으로 보입니다.

## 활성 구성 요소

```text
operations/
├── participant/
│   ├── start-jupyter             # 공용 진입점 내부 실행 파일
│   ├── session-controller.py     # 시작·상태·재접속·복구·종료
│   ├── jupyter-job.sh            # 계산 노드 Jupyter payload
│   └── site.env.example          # 공개 가능한 사이트 설정 예시
├── admin/
│   ├── participant/              # 중앙 런처 설치·검증 도구와 매뉴얼
│   └── publish-course.sh         # 검증된 commit을 중앙 release로 게시
└── KSC2026-Pilot-Validation-Guide.md
```

## 중앙과 개인 경로

```text
/scratch/hackathon/ksc2026/
├── bin/             # 모든 사용자가 실행하는 공용 명령
├── config/          # 런타임 사이트 설정
├── images/          # 중앙 ARM64 SIF와 SHA-256
├── slurm/           # 계산 노드 Jupyter payload
└── course-releases/ # 검증된 commit별 읽기 전용 강의자료

/scratch/<계정>/ksc2026/
├── session/         # 현재 Job·노드·포트·token 상태
├── workspaces/      # 사용자가 수정하는 노트북과 결과
└── logs/            # 문제 해결용 로그
```

SIF와 공용 런처를 사용자마다 복사하지 않습니다. 개인 폴더는 첫 실행 때 생성되며 mode `0700`, 관리 파일은 mode `0600`을 사용합니다.

## 중앙 배포 순서

1. `/scratch/hackathon/ksc2026`의 경로, owner, mode, canonical 경로와 symlink 여부를 확인합니다.
2. 검증된 ARM64 SIF 한 벌과 SHA-256을 중앙 경로에서 확인합니다.
3. 실제 로그인 호스트, Slurm 파티션, GRES, Apptainer, SIF, 강의 release와 24시간 제한을 private `site.env`에 기록합니다.
4. GitHub `main`의 정확한 commit을 `publish-course.sh`로 읽기 전용 release에 게시합니다.
5. 공용 런처 설치기를 dry-run한 뒤 같은 입력으로 적용합니다.
6. 시험 계정 한 개에서 `사전점검 → 시작 → 터널 → token HTTP → 저장 → 단절 → 재접속 → 종료`를 실제 검증합니다.

정적 테스트는 전체 계정의 실제 Job 실행을 뜻하지 않습니다. 행사 전 실환경 E2E는 시험 계정 한 개로 먼저 수행하고, 필요하면 별도의 소규모 동시 접속 시험을 추가합니다.

자세한 절차:

- [공용 런처 최초 배포](admin/participant/KSC2026-Shared-Launcher-Deployment-Guide.md)
- [기존 배포 갱신·복구](admin/participant/KSC2026-Admin-Deployment-Guide.md)
- [시험 사용자 E2E](KSC2026-Pilot-Validation-Guide.md)
- [사용자 실행·재접속](participant/README.md)

## 사용 명령

사용자가 기억할 명령은 세 개입니다.

```bash
# 시작 또는 기존 세션 재접속
/scratch/hackathon/ksc2026/bin/ksc2026

# 운영자가 게시한 최신 강의자료를 작업공간에 준비
/scratch/hackathon/ksc2026/bin/ksc2026 --refresh

# 현재 계정의 Job만 종료
/scratch/hackathon/ksc2026/bin/ksc2026 --stop
```

SSH나 브라우저 연결이 끊겨도 런처는 Job을 자동으로 취소하지 않습니다. 공용 명령을 다시 실행하면 활성 Job의 실제 상태를 확인하고 같은 token과 작업공간에 재접속합니다. Job이 끝난 뒤에도 저장 파일은 남지만 Python 변수, GPU 메모리와 실행 중이던 셀은 사라집니다.

## 오프라인 실행과 보안

- 계산 노드에서는 `apt`, `pip install`, `git clone`, `wget`, `curl`을 실행하지 않습니다.
- GitHub 갱신과 release 게시 작업은 인터넷이 되는 로그인 노드에서만 수행합니다.
- OTP와 비밀번호는 OpenSSH 프롬프트에만 입력하며 스크립트, 로그 또는 채팅에 저장하지 않습니다.
- Jupyter token은 활성 세션의 개인 mode `0600` 상태 파일에만 보관합니다.
- 공개 저장소에는 실제 로그인 호스트, IP 주소, 계정, token, private `site.env`와 운영 로그를 넣지 않습니다.
- `/scratch/hackathon`의 mode가 `1777`이어도 기존 공용 root를 이름만으로 신뢰하지 않습니다. 다른 owner 소유, symlink 또는 예상과 다른 파일 유형이면 중단하고 KISTI 관리자에게 확인합니다.

## 행사 전 실환경 확인

- 사용자 현장망에서 PILOT 일반 SSH와 두 번째 `ssh -N -L` 연결이 모두 가능한지
- 두 번째 SSH 연결에서 OTP·비밀번호 인증이 허용되는지
- 로그인 노드에서 동적으로 배정된 계산 노드의 Jupyter 포트로 연결되는지
- Job에 GH200이 정확히 한 개만 보이는지
- 24시간 Job, 자동 저장, 저장 파일 보존과 재접속이 동작하는지
- `/scratch/hackathon`의 계산 노드 가시성과 행사 전후 보존 정책

확인되지 않은 항목은 문서의 가정으로 넘기지 말고 실제 PILOT에서 `확인 필요`로 유지합니다.
