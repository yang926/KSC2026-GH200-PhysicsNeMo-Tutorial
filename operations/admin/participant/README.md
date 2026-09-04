# KSC 2026 공용 런타임 배포

KSC 2026 행사 사용자는 계정별 launcher나 SIF를 설치하지 않습니다. 중앙 운영자가 `/scratch/hackathon/ksc2026`에 공용 런타임 한 벌을 준비하고, 모든 사용자는 다음 명령을 실행합니다.

```bash
/scratch/hackathon/ksc2026/bin/ksc2026
```

별도 계정 분류나 고정 계산 노드표는 없습니다. 공용 런처는 Slurm `gpu` 파티션에 NVIDIA GH200 한 개를 요청하고, Slurm이 사용할 수 있는 계산 노드를 동적으로 선택합니다.

## 권한 경계

- `/scratch/hackathon`은 PILOT 로그인 노드에서 `root:root`, mode `1777`로 확인된 공용 parent입니다.
- 중앙 운영자는 `/scratch/hackathon/ksc2026`이 존재하지 않을 때 자기 계정으로 mode `0755` 디렉터리를 만듭니다.
- 기존 공용 root가 다른 owner 소유, symlink 또는 예상과 다른 파일 유형이면 중단하고 KISTI 관리자에게 확인합니다.
- 중앙 운영자와 행사 진행자는 `sudo`, `chown` 또는 관리자 비밀번호로 우회하지 않습니다.
- 중앙 SIF·런처·강의 release는 읽기 전용으로 공유하며, 개인 상태와 작업 파일은 `/scratch/$USER/ksc2026/` 아래에만 생성합니다.

## 경로 구조

```text
/scratch/hackathon/ksc2026/
├── admin/bin/       # 중앙 owner용 refresh-course
├── bin/             # 공용 ksc2026 명령
├── config/          # site.env
├── images/          # 검증된 ARM64 SIF와 SHA-256
├── slurm/           # 계산 노드 Jupyter payload
└── course-releases/ # 검증된 commit별 읽기 전용 강의자료

/scratch/<계정>/ksc2026/
├── session/
├── workspaces/
└── logs/
```

SIF는 중앙 한 벌만 두며 개인 폴더에 복사하지 않습니다.

## 운영자가 준비할 것

1. 중앙 owner 계정과 `/scratch/hackathon/ksc2026` 소유권
2. 검증된 ARM64 SIF의 절대경로·크기·SHA-256
3. KISTI가 확인한 로그인 호스트, Slurm `gpu` 파티션, GH200 GRES, Apptainer 경로와 24시간 제한
4. 최초 배포에서 게시할 GitHub `main`의 정확한 commit
5. 저장소 밖 private `site.env`
6. 시험에 사용할 PILOT 계정 한 개

실제 로그인 호스트, IP 주소, 계정, OTP, 비밀번호와 Jupyter token은 GitHub에 추가하지 않습니다.

## 공용 런타임 설치

PILOT 로그인 노드에서 중앙 owner의 새 Bash 셸을 사용합니다.

```bash
bash --noprofile --norc
KSC_CENTRAL_OWNER="$(id -un)"
KSC_SHARED=/scratch/hackathon/ksc2026
KSC_REPO="/scratch/${KSC_CENTRAL_OWNER}/ksc2026-admin/repo"
KSC_PRIVATE="/scratch/${KSC_CENTRAL_OWNER}/ksc2026-admin/private"
```

처음 생성할 때만 다음을 실행합니다.

```bash
mkdir -m 0755 "$KSC_SHARED"
mkdir -m 0700 -p "$KSC_PRIVATE"
```

공용 root와 SIF를 확인하고, 저장소 밖의 `$KSC_PRIVATE/site.env`에 실제 사이트 값을 채웁니다. placeholder, 사용자별 매핑 또는 token을 넣지 않습니다.

검증된 commit을 중앙 release에 게시한 뒤, 설치기를 먼저 dry-run합니다. 최초 배포와 공용 런타임 갱신은 정확한 소스 commit에서 신뢰 검증 도구와 중앙 owner용 `refresh-course`까지 설치하는 작업입니다.

```bash
"$KSC_REPO/operations/admin/participant/install-participants.sh" \
  --site-env "$KSC_PRIVATE/site.env" \
  --central-owner "$KSC_CENTRAL_OWNER"
```

출력의 SIF SHA-256, 중앙 경로, 설치 대상과 owner·mode를 확인합니다. 끝에 `KSC_INSTALL_MODE=DRY_RUN`, 변경 파일 수와 `KSC_INSTALL_COMPLETE=yes`가 표시되어야 합니다. 설치기는 Slurm Job을 제출하거나 취소하지 않으므로, 필요하면 설치 전후 `squeue` 결과가 같은지도 확인합니다. 예상과 모두 일치할 때만 같은 입력에 `--apply`를 추가합니다.

```bash
"$KSC_REPO/operations/admin/participant/install-participants.sh" \
  --site-env "$KSC_PRIVATE/site.env" \
  --central-owner "$KSC_CENTRAL_OWNER" \
  --apply
```

이 단계는 중앙 런타임만 설치하며 개인 디렉터리를 미리 만들거나 Slurm Job을 제출하지 않습니다.

## 이후 강의자료만 갱신

노트북, README, 실습 코드, 강의 이미지만 바뀐 경우에는 설치기를 다시 실행하지 않습니다. GitHub `main`에 push한 뒤 PILOT 로그인 노드에서 중앙 owner가 다음 한 줄을 실행합니다.

```bash
/scratch/hackathon/ksc2026/admin/bin/refresh-course
```

신뢰 게시 도구가 아직 설치되지 않은 기존 환경에 이를 처음 추가할 때는 정확한 저장소 checkout에서 설치기를 `--admin-tools-only`로 실행합니다. 이 모드는 SIF·공용 Jupyter 런타임·Slurm Job·참가자 작업공간을 검사하거나 건드리지 않고, 검증기·게시기·refresh 명령만 설치합니다.

GitHub push만으로는 중앙 게시본이 바뀌지 않습니다. 위 명령이 최신 `main` tip을 가져와 설치된 신뢰 도구로 검증하고, commit별 불변 release를 만든 뒤 중앙 설정을 원자적으로 전환합니다. 이 강의자료-only 갱신은 SIF, 공용 런타임, 활성 Slurm Job을 건드리지 않습니다.

공용 런타임을 나중에 재설치할 때 private `site.env`의 강의 release 값이 예전 commit을 가리키면, 설치기는 `SITE_ENV_COURSE_RELEASE_WOULD_ROLL_BACK`으로 중단합니다. 이 경우 현재 중앙 `config/site.env`의 release 값을 private 입력에 반영한 뒤 다시 실행합니다. 오래된 private 입력이 강의자료를 이전 버전으로 돌려놓지 않습니다.

## 실제 검증 범위

공용 배포 뒤에는 시험 계정 한 개에서 다음 E2E를 수행합니다.

1. 일반 SSH로 PILOT 로그인
2. 공용 `ksc2026` 실행
3. Slurm 동적 계산 노드·GH200 한 개 배정 확인
4. 화면의 완성된 `ssh -N -L`을 새 로컬 터미널에서 실행
5. token 인증 JupyterLab에서 렌더링된 `README.md` 첫 화면과 `00_Start_Here.ipynb` 링크 확인
6. 파일 저장
7. 터널 단절 뒤 같은 Job·작업공간 재접속
8. `--stop` 뒤 저장 파일과 중앙 SIF 불변 확인

한 계정의 E2E는 전체 동시 접속과 자원 수용량을 증명하지 않습니다. 필요한 경우 별도의 소규모 동시 접속 시험을 계획하되, 전체 계정에 Job을 일괄 제출하지 않습니다.

## 참가자 사용법

PILOT 로그인 노드에서:

```bash
/scratch/hackathon/ksc2026/bin/ksc2026
```

런처가 준비를 마치면 사용자는 새 로컬 터미널 탭에 화면의 완성된 `ssh -N -L ...` 명령을 그대로 붙여 넣고, 그다음 화면의 JupyterLab 주소를 웹 브라우저에서 엽니다.

강의자료 갱신과 종료:

```bash
/scratch/hackathon/ksc2026/bin/ksc2026 --refresh
/scratch/hackathon/ksc2026/bin/ksc2026 --stop
```

재접속할 때는 공용 명령을 다시 실행해 현재 활성 세션의 SSH 명령과 주소를 다시 확인합니다.

참가자 `--refresh`는 GitHub에서 직접 clone·pull하지 않습니다. 중앙 owner가 마지막으로 게시한 release를 새 개인 작업공간에 복사하며 기존 작업공간은 보존합니다.

## 상세 문서

- [최초 공용 배포 매뉴얼](KSC2026-Shared-Launcher-Deployment-Guide.md)
- [기존 배포 갱신·복구 매뉴얼](KSC2026-Admin-Deployment-Guide.md)
- [시험 사용자 E2E](../../KSC2026-Pilot-Validation-Guide.md)
- [사용자 실행 안내](../../participant/README.md)
