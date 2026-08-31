# KSC 2026 파일럿 검증 안내

이 문서는 KSC 2026 GH200 × PhysicsNeMo 공용 환경을 시험 사용자 한 명이 실제 KISTI PILOT에서 확인하는 절차입니다. 계정 종류에 따른 별도 경로는 없습니다. 모든 사용자는 같은 공용 명령으로 Slurm `gpu` 파티션의 NVIDIA GH200 한 개를 동적으로 배정받습니다.

검증할 전체 흐름은 다음과 같습니다.

```text
일반 SSH로 PILOT 로그인
→ 공용 ksc2026 실행
→ Slurm이 빈 GH200 1개를 동적으로 배정
→ 화면의 완성된 ssh -N -L 명령을 새 로컬 터미널에서 실행
→ 화면의 token URL을 브라우저에서 열기
→ Start Here·저장 확인
→ 터널 단절
→ 같은 Job·작업공간 재접속
→ 명시적 종료
```

실제 로그인 호스트, IP 주소, 계정, OTP, 비밀번호와 Jupyter token은 이 문서나 공개 저장소에 기록하지 않습니다.

## 운영자가 검증 전에 준비할 것

- `/scratch/hackathon/ksc2026/bin/ksc2026` 공용 명령
- `/scratch/hackathon/ksc2026/images/`의 검증된 ARM64 SIF 한 벌과 SHA-256
- 검증된 GitHub commit의 읽기 전용 중앙 강의 release
- 실제 로그인 호스트를 포함한 private `site.env`
- 시험 사용자가 자기 `/scratch/<계정>`을 만들고 쓸 수 있는 권한
- 참가자 현장망에서 PILOT에 일반 SSH와 두 번째 SSH 터널을 열 수 있는 조건

계정별 launcher, SIF 복사본, 사용자별 매핑 또는 고정 계산 노드표는 준비하지 않습니다.

## 1. 일반 SSH로 PILOT 로그인

시험 사용자는 로컬 컴퓨터의 터미널을 열고, 운영자가 별도 보안 경로로 안내한 실제 값으로 PILOT 로그인 노드에 접속합니다.

```bash
ssh <계정>@<PILOT_LOGIN_HOST>
```

OTP와 비밀번호는 OpenSSH 프롬프트에만 입력합니다. 로그인 뒤의 이 터미널을 여기서는 **PILOT 터미널**이라고 부릅니다.

확인할 것:

- 로그인 프롬프트가 PILOT 로그인 노드인지
- `id -un`이 본인의 실제 계정을 표시하는지
- `/scratch/$USER`를 본인이 쓸 수 있는지

## 2. 공용 명령 실행

PILOT 터미널에서 다음 한 줄을 실행합니다.

```bash
/scratch/hackathon/ksc2026/bin/ksc2026
```

세션이 없다면 Slurm Job을 제출하고, 활성 세션이 있다면 같은 Job으로 돌아갑니다. Slurm에는 `gpu` 파티션과 NVIDIA GH200 한 개만 요청하며 `--nodelist`나 `--exclude`로 계산 노드를 고정하지 않습니다.

대기 중에는 터미널을 닫지 않습니다. 자원이 즉시 없으면 Job이 `PENDING`일 수 있으며, 런처는 상태와 다음 행동을 분명하게 표시해야 합니다.

## 3. 배정 결과와 완성된 SSH 명령 확인

JupyterLab이 준비되면 화면에 다음 정보가 한 번씩 명확하게 표시되어야 합니다.

- 실제 계산 노드
- NVIDIA GH200 120GB 한 개와 실제 물리 GPU 번호
- 개인 작업공간
- 새 로컬 터미널에서 실행할 완성된 `ssh -N -L ...` 명령
- 브라우저에서 열 수 있는 개인 접속 token이 포함된 JupyterLab 주소

공개 문서의 형식 예시는 다음과 같으며, 실제 화면에는 모든 자리표시자가 운영 설정과 Slurm 결과로 채워져야 합니다.

```text
[1/2] 새 로컬 터미널 탭을 열고 아래 명령을 그대로 붙여 넣으세요.
ssh -N -o ExitOnForwardFailure=yes -o ServerAliveInterval=30 -o ServerAliveCountMax=3 -L 127.0.0.1:8888:<계산노드>:<원격포트> <계정>@<PILOT_LOGIN_HOST>

[2/2] 웹 브라우저에서 아래 주소를 여세요.
http://127.0.0.1:8888/lab/tree/00_Start_Here.ipynb?token=<개인 token>
```

사용자가 노드, 포트 또는 호스트를 직접 고치게 해서는 안 됩니다. `-L`은 영문 대문자 L입니다.

## 4. 새 로컬 터미널에서 SSH 터널 실행

로컬 컴퓨터에서 **새 터미널 탭**을 열고, PILOT 터미널에 출력된 SSH 명령 전체를 그대로 붙여 넣습니다. 두 번째 SSH 인증에서 OTP와 비밀번호를 다시 요청할 수 있습니다.

`ssh -N`은 원격 셸을 열지 않고 터널만 유지합니다. 인증이 끝난 뒤 프롬프트나 성공 메시지가 나타나지 않는 것이 정상입니다. 오류가 없다면 이 터미널을 닫지 않고 다음 단계로 이동합니다.

다음 오류가 보이면 결과를 그대로 기록합니다.

- `Address already in use`: 로컬 `8888` 포트 충돌
- `Connection refused`: 계산 노드 Jupyter가 아직 준비되지 않았거나 내부 경로가 닫힘
- `Permission denied`: SSH 인증 실패
- `Connection timed out`: 현장망, 로그인 호스트 또는 내부 방화벽 확인 필요

## 5. 브라우저에서 JupyterLab 열기

PILOT 터미널에 표시된 개인 접속 token이 포함된 주소를 웹 브라우저 주소창에 붙여 넣습니다. 주소는 다른 사람에게 보내거나 화면 공유에 노출하지 않습니다.

합격 기준:

- JupyterLab이 로그인 화면 없이 열림
- `00_Start_Here.ipynb`가 바로 열림
- 파일 브라우저에 `README.md`, `01_GH200/`, `02_PhysicsNeMo/`, `labs/`가 보임
- 브라우저 주소는 `127.0.0.1:8888`을 사용함

## 6. Start Here와 GPU 확인

`00_Start_Here.ipynb`의 셀을 위에서부터 실행합니다.

합격 기준:

- 아키텍처가 `aarch64` 또는 `arm64`
- PyTorch, PhysicsNeMo, PhysicsNeMo-Sym과 필수 도구가 `PASS`
- `Visible GPUs`가 정확히 `1`
- GPU 이름이 `NVIDIA GH200 120GB`
- compute capability가 `9.0`
- CUDA 텐서 연산이 `PASS`
- 드라이버가 R570 이상이며 실제 CUDA 초기화가 통과

노트북 안에서는 배정된 물리 GPU가 `cuda:0`으로 보이는 것이 정상입니다.

## 7. 저장 확인

JupyterLab에서 작은 파일을 하나 만들거나 노트북 셀을 수정한 뒤 저장합니다.

확인할 것:

- 자동 저장이 60초 간격으로 동작함
- `Cmd+S` 또는 `Ctrl+S` 뒤 저장 표시가 사라짐
- 파일이 `/scratch/<계정>/ksc2026/workspaces/` 아래에 존재함
- 다른 사용자의 작업공간이나 중앙 SIF를 수정하지 않음

## 8. 연결 단절과 재접속 확인

저장한 뒤 새 로컬 터미널의 `ssh -N -L`만 `Ctrl+C`로 종료합니다. Slurm Job은 종료하지 않습니다.

PILOT 터미널에서 공용 명령을 다시 실행합니다.

```bash
/scratch/hackathon/ksc2026/bin/ksc2026
```

다시 표시된 완성형 SSH 명령을 새 로컬 터미널 탭에서 실행하고, 다시 표시된 JupyterLab 주소를 브라우저에서 엽니다.

합격 기준:

- 중복 Job을 만들지 않고 같은 활성 세션으로 돌아감
- 계산 노드, 물리 GPU, token과 작업공간이 기존 활성 세션과 일치함
- 저장한 파일이 그대로 남아 있음
- 실행 중이던 커널이 살아 있다면 Python 변수도 유지됨

PILOT 터미널까지 끊긴 상황은 일반 SSH로 다시 로그인한 뒤 같은 공용 명령을 실행해 확인합니다.

## 9. 강의자료 갱신과 종료

운영자가 GitHub의 검증된 commit을 중앙 release로 새로 게시한 뒤, 그 강의자료를 작업공간에 준비해야 할 때만 활성 Job을 종료하고 다음 명령을 사용합니다.

```bash
/scratch/hackathon/ksc2026/bin/ksc2026 --refresh
```

검증을 마쳤다면 현재 계정의 Job만 명시적으로 종료합니다.

```bash
/scratch/hackathon/ksc2026/bin/ksc2026 --stop
```

합격 기준:

- 해당 사용자의 Job만 종료됨
- 저장한 작업공간과 로그가 남음
- 중앙 SIF의 크기, owner, mode와 SHA-256이 변하지 않음

## 전체 합격 기준

- 일반 SSH 로그인: PASS
- 공용 명령 cold start: PASS
- Slurm 동적 노드·GH200 한 개 배정: PASS
- 완성형 `ssh -N -L` 출력: PASS
- 두 번째 SSH 터널: PASS
- token 인증 JupyterLab: PASS
- Start Here: PASS
- 파일 저장: PASS
- 터널 단절 후 같은 Job 재접속: PASS
- 명시적 종료와 파일 보존: PASS
- 중앙 SIF 불변: PASS

하나라도 실패하면 전체를 완료로 기록하지 않습니다. 실패 단계, 시각, Job ID, 오류 전문과 로그 경로를 남기고 token, OTP와 비밀번호는 제거합니다.

## 결과 회신 양식

```text
KSC 2026 파일럿 검증 결과

검증 시각:
사용 환경: macOS / Windows / Linux
PILOT 로그인: PASS / FAIL
공용 명령 시작: PASS / FAIL
동적 Slurm 배정: PASS / FAIL
계산 노드:
물리 GPU 번호:
GH200 한 개 격리: PASS / FAIL
완성형 SSH 명령 출력: PASS / FAIL
두 번째 SSH 터널: PASS / FAIL
JupyterLab: PASS / FAIL
Start Here: PASS / FAIL
저장: PASS / FAIL
재접속: PASS / FAIL
종료: PASS / FAIL
중앙 SIF 불변: PASS / FAIL

실패 단계와 오류 전문:
문제가 된 노트북·셀:
추가 의견:
```

회신에는 OTP, 비밀번호, SSH 개인 키, 개인 접속 token이 포함된 URL과 실제 private 사이트 설정을 넣지 않습니다.
