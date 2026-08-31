# KSC 2026 공용 `ksc2026` 런타임 최초 배포 매뉴얼

이 문서는 PILOT 로그인 노드의 `/scratch/hackathon/ksc2026`에 행사 공용 런타임 한 벌을 처음 준비하는 절차입니다.

모든 사용자는 같은 명령을 실행하며, 별도 계정 분류나 고정 계산 노드표는 사용하지 않습니다.

```bash
/scratch/hackathon/ksc2026/bin/ksc2026
```

공용 런처는 Slurm `gpu` 파티션에 NVIDIA GH200 한 개만 요청합니다. `--nodelist`와 `--exclude`를 사용하지 않으며, Slurm이 요청 시점에 사용할 수 있는 계산 노드를 동적으로 선택합니다.

> 이 매뉴얼의 정적 검사와 dry-run은 Slurm Job을 제출하지 않습니다. 배포 완료 판정 전에는 시험 계정 한 개로 실제 시작·터널·저장·단절·재접속·종료를 검증합니다.

## 권한과 책임

- 중앙 owner: 공용 root, SIF, 사이트 설정, 런처와 강의 release를 관리하는 일반 계정
- 사용자: 자기 계정으로 공용 명령을 실행하고 `/scratch/$USER/ksc2026`에만 작업을 저장
- KISTI 관리자: 공용 parent, 파일시스템 정책, Slurm·GRES·Apptainer·내부 방화벽을 확인

중앙 owner와 행사 진행자는 `sudo`, `chown` 또는 관리자 비밀번호로 경로 문제를 우회하지 않습니다.

## 사전에 확인할 값

- 공용 parent `/scratch/hackathon`의 owner와 mode
- 공용 root를 소유할 중앙 owner 계정
- 실제 PILOT 로그인 호스트
- Slurm 파티션 `gpu`
- GH200 GRES 이름 `nvidia_gh200_120gb`
- Job 최대 시간 `1-00:00:00`
- Apptainer 절대경로
- 검증된 ARM64 SIF 절대경로·크기·SHA-256
- GitHub `main`의 게시할 정확한 40자리 commit
- 로그인 노드에서 계산 노드 Jupyter 포트로 접근 가능한 내부 네트워크 정책

실제 로그인 호스트, IP 주소, 계정, OTP, 비밀번호, SSH 키와 Jupyter token은 공개 저장소에 넣지 않습니다.

## 1. 중앙 owner 셸 준비

PILOT 로그인 노드에서 중앙 owner로 로그인하고 새 Bash 셸을 시작합니다.

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

`id -un`과 변수를 확인합니다. 환경 변수에 실제 비밀번호, OTP 또는 token을 넣지 않습니다.

## 2. 공용 parent와 root 확인

먼저 읽기 전용으로 확인합니다.

```bash
stat -c '%U:%G %a %F %n' /scratch/hackathon
readlink -f /scratch/hackathon
test ! -L /scratch/hackathon
```

확인된 계약은 `/scratch/hackathon`이 `root:root`, mode `1777`인 실제 디렉터리라는 것입니다.

공용 root가 아직 없을 때만 중앙 owner가 생성합니다.

```bash
test ! -e "$KSC_SHARED"
mkdir -m 0755 "$KSC_SHARED"
```

이미 존재한다면 이름만 보고 재사용하지 않습니다.

```bash
test -d "$KSC_SHARED"
test ! -L "$KSC_SHARED"
test "$(readlink -f "$KSC_SHARED")" = "$KSC_SHARED"
stat -c '%U:%G %a %F %n' "$KSC_SHARED"
```

중앙 owner 소유 mode `0755` 실제 디렉터리가 아니면 중단합니다. 삭제, 이름 변경, `chown` 또는 `sudo`를 시도하지 않고 KISTI 관리자에게 정확한 경로를 전달합니다.

## 3. 운영자 저장소 준비

개인 운영 경로를 만들고 저장소를 준비합니다.

```bash
mkdir -m 0700 -p "$KSC_PRIVATE"
```

`$KSC_REPO`가 없다면 로그인 노드에서 공식 KSC 저장소를 clone합니다.

```bash
git clone https://github.com/yang926/KSC2026-GH200-PhysicsNeMo-Tutorial.git "$KSC_REPO"
```

이미 있다면 먼저 변경 파일이 없는지 확인하고 fast-forward만 허용합니다.

```bash
git -C "$KSC_REPO" status --short --branch
git -C "$KSC_REPO" fetch origin main
git -C "$KSC_REPO" checkout main
git -C "$KSC_REPO" pull --ff-only origin main
KSC_COMMIT="$(git -C "$KSC_REPO" rev-parse HEAD)"
test "$(git -C "$KSC_REPO" rev-parse origin/main)" = "$KSC_COMMIT"
```

변경 파일이 있으면 `reset`이나 삭제를 하지 말고 내용을 먼저 확인합니다.

로컬 정적 검증을 실행합니다.

```bash
python3 "$KSC_REPO/tools/validate_course.py"
bash "$KSC_REPO/operations/participant/tests/run-session-tests.sh"
bash "$KSC_REPO/operations/admin/participant/tests/run-tests.sh"
```

모두 통과하기 전에는 중앙 배포를 진행하지 않습니다.

## 4. 중앙 SIF 확인

행사 SIF는 다음 중앙 경로의 한 벌만 사용합니다.

```text
/scratch/hackathon/ksc2026/images/ksc2026-gh200-physicsnemo_25.11-arm64.sif
```

파일과 sidecar SHA-256을 확인합니다.

```bash
KSC_SIF="$KSC_SHARED/images/ksc2026-gh200-physicsnemo_25.11-arm64.sif"
test -f "$KSC_SIF"
test ! -L "$KSC_SIF"
sha256sum --check --strict "${KSC_SIF}.sha256"
stat -c '%U:%G %a %s %n' "$KSC_SIF" "${KSC_SIF}.sha256"
```

SIF가 없거나 SHA-256이 다르면 런처 배포를 중단합니다. 계산 노드나 사용자 노트북에서 이미지를 내려받거나 빌드하지 않습니다. KISTI가 승인한 전송·빌드 경로에서 검증을 마친 뒤 중앙 한 벌만 배치합니다.

## 5. private `site.env` 준비

공개 예시를 private 경로에 mode `0600`으로 복사한 뒤 실제 KISTI 값으로 채웁니다.

```bash
install -m 0600 \
  "$KSC_REPO/operations/participant/site.env.example" \
  "$KSC_SITE_ENV"
```

최종 설정에는 다음 계약이 포함되어야 합니다.

- 공용 root와 실제 로그인 호스트
- Slurm `gpu` 파티션에서 GH200 한 개를 요청하는 GRES 설정
- 24시간 제한과 Jupyter 준비 제한시간
- Apptainer와 중앙 SIF 절대경로·SHA-256
- 중앙 강의 release 경로·저장소·branch
- 계산 노드 payload 절대경로
- `/scratch/{user}/ksc2026/session`
- `/scratch/{user}/ksc2026/workspaces`
- `/scratch/{user}/ksc2026/logs`
- 로컬 Jupyter 포트 `8888`

`site.env`는 셸 스크립트가 아니라 `KEY=VALUE` 데이터입니다. `source`하지 않으며, placeholder가 남아 있으면 설치기가 중단해야 합니다. 사용자별 매핑, 고정 노드, 고정 GPU와 token은 넣지 않습니다.

## 6. 정확한 Git commit 게시

로그인 노드에서 검증한 정확한 commit을 읽기 전용 release로 게시합니다.

```bash
"$KSC_REPO/operations/admin/publish-course.sh" \
  --root "$KSC_SHARED" \
  --site-env "$KSC_SITE_ENV" \
  --ref main \
  --commit "$KSC_COMMIT"
```

게시 뒤 다음을 확인합니다.

```bash
test -d "$KSC_SHARED/course-releases/$KSC_COMMIT"
test ! -L "$KSC_SHARED/course-releases/$KSC_COMMIT"
test -f "$KSC_SHARED/course-releases/$KSC_COMMIT/00_Start_Here.ipynb"
test -f "$KSC_SHARED/course-releases/$KSC_COMMIT/README.md"
```

사용자가 수정하는 것은 이 중앙 release가 아니라 첫 실행 때 복사되는 개인 작업공간입니다.

## 7. 공용 런타임 dry-run과 적용

먼저 변경 없는 dry-run을 실행합니다.

```bash
"$KSC_REPO/operations/admin/participant/install-participants.sh" \
  --site-env "$KSC_SITE_ENV" \
  --central-owner "$KSC_CENTRAL_OWNER"
```

다음을 확인합니다.

- source가 예상한 `$KSC_COMMIT`
- SIF 경로·SHA-256이 검증값과 일치
- Slurm 파티션이 `gpu`, GRES가 GH200 한 개
- 노드 고정 또는 제외 옵션이 없음
- 설치 대상이 `$KSC_SHARED` 아래로 제한
- 실제 로그인 호스트가 공개 코드가 아니라 private 설정에서 제공됨
- `SLURM_SUBMISSIONS=0`, `SLURM_CANCELLATIONS=0`

모두 일치할 때만 같은 입력에 `--apply`를 추가합니다.

```bash
"$KSC_REPO/operations/admin/participant/install-participants.sh" \
  --site-env "$KSC_SITE_ENV" \
  --central-owner "$KSC_CENTRAL_OWNER" \
  --apply
```

이 작업은 중앙 공용 런타임만 설치합니다. 개인 `/scratch/<계정>/ksc2026`을 미리 만들거나 SIF를 복사하거나 Slurm Job을 제출하지 않습니다.

## 8. 설치 readback

설치가 끝나면 중앙 파일을 다시 읽습니다.

```bash
stat -c '%U:%G %a %F %n' \
  "$KSC_SHARED" \
  "$KSC_SHARED/bin" \
  "$KSC_SHARED/bin/ksc2026" \
  "$KSC_SHARED/config/site.env" \
  "$KSC_SHARED/slurm/jupyter-job.sh"

test -x "$KSC_SHARED/bin/ksc2026"
test -r "$KSC_SHARED/config/site.env"
sha256sum --check --strict "${KSC_SIF}.sha256"
```

공용 명령과 중앙 SIF는 사용자가 읽고 실행할 수 있어야 하지만 group/other가 수정할 수 없어야 합니다. private 설정 원본과 배포본의 민감도·가시성은 KISTI 정책에 맞춰 별도로 확인합니다.

## 9. 시험 계정 한 개의 실제 E2E

시험 사용자는 일반 SSH로 PILOT에 로그인한 뒤 공용 명령을 실행합니다.

```bash
/scratch/hackathon/ksc2026/bin/ksc2026
```

런처 출력에서 Slurm이 동적으로 선택한 계산 노드와 GH200 한 개를 확인합니다. 새 로컬 터미널 탭에서 화면의 완성된 `ssh -N -L ...` 명령을 그대로 실행하고, 그다음 개인 접속 token이 포함된 주소를 브라우저에서 엽니다.

다음 항목을 실제로 검증합니다.

- `00_Start_Here.ipynb`가 열림
- PyTorch에서 GPU가 정확히 한 개 보임
- 파일이 `/scratch/<계정>/ksc2026/workspaces/`에 저장됨
- 터널만 끊은 뒤 공용 명령을 다시 실행하면 같은 Job으로 돌아감
- `--stop`은 해당 계정의 Job만 종료함
- 중앙 SIF의 SHA-256이 변하지 않음

전체 절차는 [파일럿 검증 안내](../../KSC2026-Pilot-Validation-Guide.md)를 따릅니다.

## 10. 강의자료 갱신

노트북, README, 실습 코드 또는 강의 이미지만 바뀌었을 때는 SIF와 공용 런타임을 다시 설치하지 않습니다.

1. GitHub `main`에 검증된 변경을 push합니다.
2. 중앙 owner 저장소를 fast-forward합니다.
3. 새 commit을 `publish-course.sh`로 게시합니다.
4. 활성 Job을 종료한 사용자가 다음 명령으로 새 작업공간을 준비합니다.

```bash
/scratch/hackathon/ksc2026/bin/ksc2026 --refresh
```

기존 작업공간은 삭제하거나 덮어쓰지 않습니다.

## 공개하거나 전송하지 않을 것

- 실제 PILOT 로그인 호스트와 IP 주소
- 실제 계정, OTP, 비밀번호와 SSH 키
- private `site.env`
- 개인 접속 token이 포함된 JupyterLab 주소와 활성 세션 상태
- 운영 로그 원문

공개 예시에는 `<PILOT_LOGIN_HOST>`, `<계정>`, `<계산노드>`와 같은 자리표시자만 사용합니다.
