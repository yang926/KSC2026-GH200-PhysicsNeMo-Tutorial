# KSC 2026 공용 런타임 상세 운영 매뉴얼

이 문서는 이미 설치된 `/scratch/hackathon/ksc2026` 공용 런타임을 점검·갱신·복구하는 중앙 owner용 절차입니다. 최초 설치는 [공용 런타임 최초 배포 매뉴얼](KSC2026-Shared-Launcher-Deployment-Guide.md)을 먼저 따릅니다.

모든 사용자는 같은 공용 명령과 같은 자원 계약을 사용합니다.

```bash
/scratch/hackathon/ksc2026/bin/ksc2026
```

- Slurm `gpu` 파티션
- NVIDIA GH200 한 개
- `--nodelist`, `--exclude` 없음
- Slurm의 동적 계산 노드 배정
- 최대 24시간
- 개인 경로 `/scratch/$USER/ksc2026/{session,workspaces,logs}`

별도 계정 분류나 고정 계산 노드표는 없습니다.

운영 작업은 두 가지로 구분합니다.

- **강의자료-only 갱신:** GitHub `main`에 push한 뒤 설치된 `/scratch/hackathon/ksc2026/admin/bin/refresh-course`를 한 번 실행합니다. SIF·공용 런타임·활성 Job은 바꾸지 않습니다.
- **신뢰 도구·공용 런타임 갱신:** 정확한 Git commit을 다시 검증하고 설치기를 dry-run·갱신합니다. 이 경로에서는 실행 중인 사용자 Job에 대한 영향을 먼저 확인합니다.

GitHub push만으로 서버가 자동 변경되지는 않습니다. 중앙 owner의 명시적인 게시 명령이 있어야 새 commit이 중앙 release로 활성화됩니다.

## 권한 모델

- 중앙 owner만 공용 root의 런처·설정·release를 갱신합니다.
- 사용자는 공용 파일을 읽고 실행하며 자기 `/scratch` 작업공간만 수정합니다.
- 중앙 owner와 행사 진행자는 `sudo`, `chown` 또는 관리자 비밀번호로 권한 문제를 우회하지 않습니다.
- `/scratch/hackathon/ksc2026`이 다른 owner 소유, symlink 또는 예상과 다른 파일 유형이면 변경하지 않고 KISTI 관리자에게 확인합니다.
- 기존 작업공간, release, SIF와 로그를 자동 삭제하지 않습니다. 교체가 필요하면 먼저 timestamp archive로 보존합니다.

## 중앙 구조

```text
/scratch/hackathon/ksc2026/
├── admin/
│   └── bin/
│       └── refresh-course
├── bin/
│   └── ksc2026
├── config/
│   └── site.env
├── images/
│   ├── ksc2026-gh200-physicsnemo_25.11-arm64.sif
│   └── ksc2026-gh200-physicsnemo_25.11-arm64.sif.sha256
├── slurm/
│   └── jupyter-job.sh
└── course-releases/
    └── <40자리 commit>/
```

개인 경로:

```text
/scratch/<계정>/ksc2026/
├── session/
├── workspaces/
└── logs/
```

## 1. 현재 상태를 읽기 전용으로 확인

PILOT 로그인 노드에서 중앙 owner의 새 Bash 셸을 사용합니다.

```bash
bash --noprofile --norc
umask 077

KSC_CENTRAL_OWNER="$(id -un)"
KSC_SHARED=/scratch/hackathon/ksc2026
KSC_ADMIN_ROOT="/scratch/${KSC_CENTRAL_OWNER}/ksc2026-admin"
KSC_REPO="${KSC_ADMIN_ROOT}/repo"
KSC_PRIVATE="${KSC_ADMIN_ROOT}/private"
KSC_SITE_ENV="${KSC_PRIVATE}/site.env"
```

경로와 권한을 확인합니다.

```bash
stat -c '%U:%G %a %F %n' /scratch/hackathon "$KSC_SHARED"
readlink -f /scratch/hackathon "$KSC_SHARED"
test ! -L "$KSC_SHARED"

stat -c '%U:%G %a %F %n' \
  "$KSC_SHARED/bin/ksc2026" \
  "$KSC_SHARED/config/site.env" \
  "$KSC_SHARED/slurm/jupyter-job.sh"
```

Slurm 상태를 읽습니다.

```bash
squeue --noheader --format='%A|%u|%T|%N|%j'
```

공용 런타임을 갱신하기 전에 관련 활성 Job이 있는지 확인합니다. 실행 중인 사용자 Job을 설치기가 자동 종료하게 해서는 안 됩니다.

## 2. 신뢰 도구·공용 런타임 갱신 시 저장소 확인

이 절은 중앙에 설치된 검증 도구나 공용 런타임 코드를 바꿀 때만 수행합니다. 노트북·README·실습 코드·강의 이미지만 바뀐 경우에는 [9. 강의자료만 갱신](#9-강의자료만-갱신)을 따릅니다.

```bash
git -C "$KSC_REPO" status --short --branch
git -C "$KSC_REPO" fetch origin main
git -C "$KSC_REPO" log --oneline --decorate -5 main origin/main
```

변경 파일이 있으면 `reset`, checkout 덮어쓰기 또는 삭제를 하지 않습니다. 차이를 검토하고 보존한 뒤에만 fast-forward합니다.

```bash
git -C "$KSC_REPO" checkout main
git -C "$KSC_REPO" pull --ff-only origin main
KSC_COMMIT="$(git -C "$KSC_REPO" rev-parse HEAD)"
test "$(git -C "$KSC_REPO" rev-parse origin/main)" = "$KSC_COMMIT"
```

## 3. 로컬 정적 검증

```bash
python3 "$KSC_REPO/tools/validate_course.py"
bash "$KSC_REPO/operations/participant/tests/run-session-tests.sh"
bash "$KSC_REPO/operations/admin/participant/tests/run-tests.sh"
git -C "$KSC_REPO" diff --check
```

정적 검증은 전체 사용자의 실제 Slurm·GPU·네트워크 동작을 증명하지 않습니다. 실패한 검사를 건너뛰고 배포하지 않습니다.

## 4. 중앙 SIF 불변 확인

```bash
KSC_SIF="$KSC_SHARED/images/ksc2026-gh200-physicsnemo_25.11-arm64.sif"
test -f "$KSC_SIF"
test ! -L "$KSC_SIF"
sha256sum --check --strict "${KSC_SIF}.sha256"
stat -c '%U:%G %a %s %y %n' "$KSC_SIF" "${KSC_SIF}.sha256"
```

노트북, README, 실습 코드 또는 강의 이미지만 바뀌었다면 SIF를 교체하지 않습니다. Python, PhysicsNeMo, CUDA, NVHPC 또는 시스템 라이브러리가 바뀔 때만 별도의 이미지 빌드·검증 절차가 필요합니다.

## 5. private `site.env` 검토

설치 입력은 저장소 밖 `$KSC_SITE_ENV`입니다. 셸로 `source`하지 않고 데이터로만 검증합니다.

확인할 계약:

- 공용 root와 실제 로그인 호스트
- Slurm `gpu` 파티션에서 GH200 한 개를 요청하는 GRES 설정
- 24시간 제한
- `--nodelist`와 `--exclude`가 없는 동적 배정
- Apptainer와 중앙 SIF 경로·SHA-256
- 현재 중앙 강의 release
- 계산 노드 payload
- `/scratch/{user}/ksc2026/session`
- `/scratch/{user}/ksc2026/workspaces`
- `/scratch/{user}/ksc2026/logs`
- 로컬 포트 `8888`

사용자별 매핑, 고정 계산 노드, 고정 GPU, OTP, 비밀번호와 token을 넣지 않습니다. 실제 로그인 호스트와 IP 주소는 private 설정과 서버 출력에만 둡니다.

private `site.env`는 실제 사이트 값의 설치 입력이지 현재 게시된 강의 release의 최신 대장이 아닙니다. 강의자료를 여러 번 게시한 뒤 예전 private `site.env`로 공용 런타임을 재설치하면, 설치기는 `SITE_ENV_COURSE_RELEASE_WOULD_ROLL_BACK`으로 중단하고 중앙 설정을 바꾸지 않습니다. 현재 중앙 `config/site.env`의 release 값을 private 입력에 반영한 뒤 다시 실행합니다.

## 6. 공용 런타임 dry-run

```bash
"$KSC_REPO/operations/admin/participant/install-participants.sh" \
  --site-env "$KSC_SITE_ENV" \
  --central-owner "$KSC_CENTRAL_OWNER"
```

다음을 확인합니다.

- source commit이 예상한 `$KSC_COMMIT`
- SIF path·SHA-256이 중앙 불변값과 일치
- 설치 대상이 `$KSC_SHARED` 아래로 제한
- Slurm 계약이 `gpu` 파티션·GH200 한 개·동적 노드 배정
- 완성형 SSH 명령에 필요한 로그인 호스트가 private 설정에서 제공됨
- 설치 전후 `squeue` 결과가 같고 새 `ksc26-jlab-*` Job이 생기거나 취소되지 않음

dry-run이 실제 파일이나 Slurm 상태를 바꾸면 실패입니다.

## 7. 공용 런타임 적용과 readback

활성 Job의 영향과 dry-run을 확인한 뒤 같은 입력에 `--apply`를 추가합니다.

```bash
"$KSC_REPO/operations/admin/participant/install-participants.sh" \
  --site-env "$KSC_SITE_ENV" \
  --central-owner "$KSC_CENTRAL_OWNER" \
  --apply
```

적용 뒤 실제 설치본을 다시 읽습니다.

```bash
stat -c '%U:%G %a %F %n' \
  "$KSC_SHARED/admin/bin/refresh-course" \
  "$KSC_SHARED/bin/ksc2026" \
  "$KSC_SHARED/config/site.env" \
  "$KSC_SHARED/slurm/jupyter-job.sh"

test -x "$KSC_SHARED/bin/ksc2026"
test -x "$KSC_SHARED/admin/bin/refresh-course"
test -r "$KSC_SHARED/config/site.env"
sha256sum --check --strict "${KSC_SIF}.sha256"
```

설치기는 개인 `/scratch/<계정>`에 파일을 만들거나 SIF를 복사하거나 Slurm Job을 제출하지 않아야 합니다.

## 8. 시험 계정 한 개로 실환경 검증

시험 사용자가 일반 SSH로 PILOT에 로그인한 뒤 다음을 실행합니다.

```bash
/scratch/hackathon/ksc2026/bin/ksc2026
```

성공 화면에서 다음을 확인합니다.

- Slurm이 동적으로 선택한 실제 계산 노드
- NVIDIA GH200 120GB 한 개와 물리 GPU 번호
- `/scratch/<계정>/ksc2026/workspaces/` 개인 작업공간
- 실제 계정·로그인 호스트·계산 노드·포트가 모두 채워진 한 줄 `ssh -N -L ...`
- 개인 접속 token이 포함된 JupyterLab 주소

새 로컬 터미널 탭에서 출력된 SSH 명령을 그대로 실행합니다. 인증 뒤 아무 메시지 없이 터널이 유지되는 것이 정상입니다. 브라우저에서 URL을 열고 다음을 확인합니다.

- `README.md`가 렌더링된 첫 화면으로 열리고 상단 링크에서 `00_Start_Here.ipynb`가 열림
- PyTorch에서 GH200이 정확히 한 개 보임
- CUDA 텐서 연산이 통과
- 파일 저장과 60초 자동 저장
- 터널 단절 뒤 공용 명령 재실행 시 같은 Job·token·작업공간 재접속
- `--stop` 뒤 해당 Job만 종료되고 저장 파일은 유지
- 중앙 SIF SHA-256 불변

자세한 체크리스트는 [파일럿 검증 안내](../../KSC2026-Pilot-Validation-Guide.md)를 따릅니다.

## 9. 강의자료만 갱신

노트북, README, 실습 코드, 강의 이미지만 바뀐 경우에는 SIF나 공용 런타임을 다시 설치하지 않습니다. 검증된 변경을 GitHub `main`에 push한 뒤, PILOT 로그인 노드에서 중앙 owner가 설치된 명령을 한 번 실행합니다.

```bash
/scratch/hackathon/ksc2026/admin/bin/refresh-course
```

이 명령은 다음 작업을 한 번에 수행합니다.

1. 허용된 GitHub 저장소의 `main` 최신 tip을 가져옵니다.
2. 가져온 트리를 실행 코드가 아닌 검증 대상 데이터로 취급하고, 최초 배포 때 설치한 신뢰 검증 도구로 검사합니다.
3. 검증을 통과한 40자리 commit만 새 읽기 전용 `course-releases/<commit>/`으로 게시합니다.
4. 중앙 `config/site.env`가 새 release를 가리키도록 원자적으로 전환합니다.

명령이 끝나면 출력된 commit과 활성 release 경로가 GitHub `main`의 기대 commit과 일치하는지 확인합니다. 검증이 실패하면 이전 중앙 release를 그대로 유지하고 원인을 해결한 뒤 다시 실행합니다. GitHub push만으로는 중앙 게시본이 바뀌지 않습니다.

공개 저장소에서 민감정보 제거 등을 위해 Git 이력을 교체한 직후에는 기존
활성 release의 commit과 새 `main`이 fast-forward 관계가 아닐 수 있습니다.
이 경우 일반 `refresh-course`는 안전하게 중단됩니다. 중앙 owner가 현재
활성 release의 40자리 commit과 새로 검증한 40자리 commit을 각각 확인한
뒤에만 다음 세 값을 모두 고정해 일회성 전환을 수행합니다.

```bash
"$KSC_SHARED/admin/libexec/publish-course.sh" \
  --root "$KSC_SHARED" \
  --site-env "$KSC_SHARED/config/site.env" \
  --ref main \
  --commit "$KSC_NEW_COMMIT" \
  --frozen-commit "$KSC_NEW_COMMIT" \
  --migrate-from-commit "$KSC_CURRENT_COMMIT"
```

현재 활성 release가 `--migrate-from-commit`과 정확히 일치하지 않거나,
목표 `main` tip을 `--commit`과 `--frozen-commit`에 동일하게 지정하지 않으면
게시기는 변경 전에 중단합니다. 기존 release의 manifest·권한 검증도
그대로 수행하며, SIF·공용 런타임·Job·개인 작업공간은 변경하지 않습니다.

이 절차는 중앙 SIF, 공용 `ksc2026` 런타임, 실행 중인 Slurm Job과 기존 개인 작업공간을 변경하지 않습니다. 새 게시본을 사용할 참가자만 현재 파일을 저장하고 자기 Job을 종료한 뒤 다음 명령으로 새 작업공간을 준비합니다.

```bash
/scratch/hackathon/ksc2026/bin/ksc2026 --refresh
```

기존 작업공간은 삭제하거나 덮어쓰지 않습니다. 수업 중인 활성 작업공간이 자동으로 새 commit으로 바뀌지 않아야 합니다.

## 10. 사용자 종료

수업을 마치거나 release를 바꾸기 전에 사용자가 자기 Job을 종료합니다.

```bash
/scratch/hackathon/ksc2026/bin/ksc2026 --stop
```

중앙 운영자가 다른 사용자의 Job을 일괄 취소하는 것은 기본 절차가 아닙니다. 비상 종료가 필요하면 대상 Job과 영향 범위를 읽기 전용으로 확인하고 KISTI 운영 정책에 따릅니다.

## 11. 실패와 복구

### 공용 root가 예상과 다름

삭제, 이름 변경, `chown` 또는 `sudo`를 실행하지 않습니다. `stat`, `readlink -f` 결과와 정확한 경로를 KISTI 관리자에게 전달합니다.

### SIF SHA-256 불일치

Job을 시작하지 않습니다. sidecar와 파일 출처를 확인하고 검증된 SIF를 별도 경로에 다시 준비합니다. 불일치 파일을 정상 이름으로 덮어쓰지 않습니다.

### Slurm Job이 계속 PENDING

`squeue`와 `scontrol show job <JOB_ID>`에서 이유를 확인합니다. 특정 노드를 강제로 지정하거나 제외해 우회하지 않습니다. 자원, partition, GRES, reservation과 정책은 KISTI에 확인합니다.

### SSH 터널 실패

- `Address already in use`: 로컬 `8888` 포트 사용 상태 확인
- `Connection refused`: Jupyter 준비 상태와 로그인 노드→계산 노드 내부 연결 확인
- `Permission denied`: 두 번째 SSH 인증 확인
- timeout: 현장망·로그인 호스트·내부 방화벽 확인

### 런타임 적용 실패

부분 적용 상태를 추정하지 않습니다. 설치 로그, 중앙 파일의 owner·mode·SHA-256과 Git commit을 다시 읽고, 검증된 이전 설치본이 있으면 timestamp archive와 운영자가 확인한 metadata를 근거로 복구합니다. 사용자 작업공간은 삭제하지 않습니다.

## 12. 공개 저장소에 넣지 않을 것

- 실제 로그인 호스트와 IP 주소
- 실제 계정, OTP, 비밀번호와 SSH 키
- private `site.env`
- 개인 접속 token이 포함된 브라우저 주소와 활성 세션 파일
- 운영 로그 원문

공개 문서와 테스트 fixture에는 자리표시자나 합성 값만 사용합니다.
