# KSC 2026 통합 GH200·PhysicsNeMo 배포·접속 가이드

이 문서는 운영자가 **KISTI의 ARM64 로그인 서버에서 Apptainer로 SIF를 직접 만들고 통합 공용 런처를 배포**하는 절차를 설명합니다. Docker 이미지가 이미 있는 환경을 위한 Docker→SIF 경로도 그대로 제공합니다. 계산 노드에서는 인터넷 연결, 패키지 설치, 소스 코드 내려받기를 사용하지 않습니다. 참가자 한 명이 Slurm으로 배정된 GH200 한 개를 사용하는 구성을 전제로 하지만, 실제 PILOT 할당 방식과 GPU 격리는 운영팀 확인이 필요합니다.

## 1. 현재 준비 상태와 실제 환경에서 확인할 항목

| 항목 | 현재 구성 | 실제 배포 전 확인 |
|---|---|---|
| 아키텍처 | `linux/arm64` | 빌드 결과의 `Architecture=arm64` |
| PhysicsNeMo | 25.11 ARM64 이미지 매니페스트 고정 | NGC 접근 권한, PILOT 드라이버 호환성 |
| GH200 컴파일러·수치 라이브러리 | NVHPC 25.5 + NVPL 25.5 | `nvc -V`, NVPL 연결·실행 |
| Boost.ProgramOptions | Boost 1.83.0에서 필요한 정적 라이브러리만 빌드 | 정적 연결 여부, BSL-1.0 고지 보존 |
| CPU BLAS | OpenBLAS 0.3.31 | DGEMM 컴파일·실행 |
| CUDA·프로파일링 | 기반 이미지의 `nvcc`, `nsys` | GH200에서 컴파일·실행·프로파일 생성 |
| 전송 대역폭 | nvbandwidth 0.8, SM90 대상 빌드 | 제한된 호스트↔디바이스 전송 테스트 |
| 노트북 | 기반 이미지의 JupyterLab | SSH 포트 포워딩, 포트, 영구 작업 경로 |
| 실행 중 인터넷 | 필요 없음 | 인터넷을 차단한 상태에서 전체 실습 완주 |

Dockerfile·Apptainer 정의 파일·검증 스크립트의 정적 검사를 통과하는 것과, 실제 ARM64 SIF를 빌드해 PILOT GH200에서 전체 실습을 마치는 것은 서로 다른 단계입니다. 아래 사전 점검과 모든 노트북의 예행연습을 마쳐야 행사 준비가 완료된 것으로 판단합니다.

2026-08-28 KISTI ARM64 환경에서 직접 Apptainer 빌드가 완료되었습니다.

- SIF: `/scratch/<빌드계정>/ksc2026/images/ksc2026-gh200-physicsnemo_25.11-arm64.sif`
- 크기: 21,765,976,064 bytes
- SHA-256: `ee43b2c0735b26a7168e53c7e598dd5dc527b1e23284682f790430656d8bdacf`
- 빌드 기준 강의자료 commit: `937f56f2aea90a752aa4b490895c5feaae524429`

SIF 체크섬은 2026-08-29 다시 확인해 `OK`가 출력되었습니다. GH200 필수 노트북과 Jupyter를 포함한 후속 postbuild 실행 검증은 별도 로그로 판정하며, 그 검증이 끝나기 전에는 전체 행사 준비가 완료된 것으로 표시하지 않습니다.

컴파일러나 NVPL 실행 파일이 빠질 위험을 줄이기 위해 NVHPC의 `/opt/nvidia/hpc_sdk` 전체를 복사하므로 컨테이너 이미지가 큽니다. 처음 빌드에 성공하면 SIF의 크기와 PILOT 전송 시간을 기록하세요. Docker 대안 경로를 사용했다면 Docker 이미지 아카이브의 크기도 함께 기록합니다. 크기를 줄여야 한다면 컴파일·연결·실행 회귀 검사를 유지한 상태에서 필요한 하위 경로만 남겨야 합니다.

## 2. 컨테이너 이미지에 들어가는 것

최종 컨테이너 이미지에는 다음 항목을 미리 포함합니다.

- NVIDIA PhysicsNeMo 25.11 ARM64 기반 이미지
- NVIDIA HPC SDK 25.5와 그 배포본에 포함된 NVPL 25.5
- Boost 1.83.0의 ProgramOptions 정적 라이브러리
- OpenBLAS 0.3.31
- nvbandwidth 0.8
- 기반 이미지에서 미리 확인한 C/C++ 컴파일러, `make`, CMake, 압축·SHA-256 도구와 `nvc`, `nvcc`, `nsys`, JupyterLab
- 비상용으로 내장한 참가자 필수 노트북 5개(`00` + GH200 2개 + PhysicsNeMo 2개), `02_PhysicsNeMo/optional/`의 FNO 선택 실습, `labs/`, `assets/`
- 이미지 구성 정보, 강의자료 체크섬, 제3자 소스 코드·라이선스 정보
- 참가자 접속과 서버 운영에 필요한 `operations/` 스크립트

컨테이너 이미지 안의 `/opt/ksc2026/course-source`는 빌드 시점의 비상용 자료입니다. 참가자 운영에서는 로그인 노드의 `publish-course.sh`가 GitHub의 검증된 commit을 읽기 전용 공유 release로 게시합니다. 계산 노드 시작 스크립트는 이 release를 `/opt/ksc2026/course-source`에 읽기 전용으로 연결하고, 최초 실행 때 `course-release.json`의 `participant_paths`만 개인 `/scratch`의 commit별 쓰기 가능한 작업 폴더로 복사합니다. Jupyter는 이 개인 작업 폴더를 작업 경로로 사용하므로 재접속 시 수정본을 이어 쓰고, 새 commit이 기존 결과를 덮어쓰지 않습니다.

강사와 수강생을 구분하는 별도 런처는 사용하지 않습니다. PILOT에 로그인할 수 있는 모든 사용자는 같은 공용 명령을 실행하고, Slurm에서 GH200 한 개를 동적으로 배정받습니다. Jupyter가 쓰는 위치는 각 계정의 개인 `/scratch` 작업 폴더이며, 공유 release나 SIF 내부 비상용 자료를 직접 수정하지 않습니다.

비공개 GH200 저장소의 노트북·PPT·소스 코드는 이 빌드에 포함하지 않습니다. Docker 경로에서는 `.dockerignore`, KISTI 직접 빌드 경로에서는 `Apptainer.kisti.def`의 파일별 허용 목록을 사용해 공개 강의 저장소에 둘 수 있는 파일만 이미지에 넣습니다.

## 3. 고정 버전과 소스 코드 검증

세부 값은 [`container/third-party-sources.json`](container/third-party-sources.json)에 있습니다.

| 기반 이미지 | 고정 값 |
|---|---|
| PhysicsNeMo 25.11 ARM64 이미지 매니페스트 | `sha256:4e7f82e33d886828efd1e4d65236f5e44c96dfbd3d316c58723eff9b9298eda6` |
| NVHPC 25.5 ARM64 이미지 매니페스트 | `sha256:d5b8001ed137d70417454279c46f6dde335337efbbd6742a4b1c103cbf85831b` |

소스에서 만드는 종속성은 다음 URL과 SHA-256으로 고정합니다.

| 구성 | 고정 소스 URL | SHA-256 | 빌드·고지 범위 |
|---|---|---|---|
| Boost 1.83.0 | `https://archives.boost.io/release/1.83.0/source/boost_1_83_0.tar.gz` | `c0685b68dd44cc46574cce86c4e17c0f611b15e195be9848dfd0769a0a207628` | ProgramOptions만 정적 라이브러리로 빌드, BSL-1.0 `LICENSE_1_0.txt` 보존 |
| OpenBLAS 0.3.31 | `https://github.com/OpenMathLib/OpenBLAS/releases/download/v0.3.31/OpenBLAS-0.3.31.tar.gz` | `6dd2a63ac9d32643b7cc636eab57bf4e57d0ed1fff926dfbc5d3d97f2d2be3a6` | C 언어 부분만 빌드, BSD-3-Clause 라이선스 보존 |
| nvbandwidth 0.8 | `https://github.com/NVIDIA/nvbandwidth/archive/refs/tags/v0.8.tar.gz` | `b3622945eb7fce2b4e1aea7d13de04f415f4d998db602893201a904320cf2d39` | SM90 대상으로 빌드, Apache-2.0과 함께 제공되는 고지 보존 |

KISTI 직접 빌드는 운영체제의 패키지 관리자를 사용하지 않습니다. 먼저 기반 이미지에 필요한 컴파일러, `make`, CMake, 다운로드·압축 해제·SHA-256 검증 도구가 모두 있는지 검사하고, 하나라도 없으면 소스 다운로드 전에 중단합니다. 세 소스 압축 파일은 SHA-256이 일치할 때만 빌드하며, NVIDIA 기반 이미지는 위 ARM64 매니페스트 다이제스트로 고정합니다.

## 4. KISTI 권장 경로: Apptainer로 SIF 직접 만들기

현재 확인한 KISTI PILOT 로그인 환경은 ARM64이며 인터넷에 연결되어 있고 `apptainer/1.4.5` 모듈을 제공합니다. 이 환경에서는 Docker나 Podman을 거치지 않고 저장소 최상위 폴더에서 다음과 같이 실행합니다. 루트 권한 없이 실행한 Podman(rootless Podman)은 NFS의 확장 속성(xattr) 처리 단계에서 실패했으므로 KISTI 권장 경로로 사용하지 않습니다.

```bash
module load apptainer/1.4.5
./container/build_kisti_sif.sh
```

`container/Apptainer.kisti.def`는 NVHPC 25.5 ARM64 이미지와 PhysicsNeMo 25.11 ARM64 이미지를 각각 고정한 다이제스트로 가져오는 2단계 정의 파일입니다. 앞 단계의 `/opt/nvidia/hpc_sdk` 전체를 최종 단계로 복사합니다. 최종 기반 이미지의 빌드 도구를 먼저 검사한 뒤, Boost 1.83.0 ProgramOptions 정적 라이브러리, OpenBLAS 0.3.31, nvbandwidth 0.8을 위 표의 소스와 SHA-256으로 빌드합니다. 이 직접 빌드 경로에서는 `apt`나 `apt-get`을 실행하지 않습니다. 강의자료와 운영 스크립트는 파일별 허용 목록에 있는 항목만 SIF에 넣습니다.

빌드 스크립트는 다음 안전장치를 적용합니다.

- ARM64와 Apptainer 1.4 이상인지 확인
- 기반 이미지의 빌드 도구를 소스 다운로드 전에 확인하고, 누락 시 중단
- `APPTAINER_CACHEDIR`와 `APPTAINER_TMPDIR`를 지정한 스크래치로 분리
- Apptainer 임시 경로가 NFS이면 중단
- Boost.ProgramOptions·OpenBLAS·nvbandwidth 컴파일과 SIF 압축 작업의 병렬도를 최대 12개로 제한
- `%test`와 빌드 뒤 정적 기본 동작 점검을 모두 통과한 SIF만 최종 경로로 이동
- SIF와 같은 폴더에 `.sha256` 생성 후 즉시 재검사

기본 출력은 `dist/ksc2026-gh200-physicsnemo_25.11-arm64.sif`입니다. 다른 경로를 쓰려면 첫째 인자로 지정합니다.

```bash
./container/build_kisti_sif.sh /scratch/hackathon/ksc2026/images/ksc2026-gh200-physicsnemo_25.11-arm64.sif
```

스크립트는 `KSC_BUILD_SCRATCH`, 사이트의 `SCRATCH`, 사용자별 `/tmp` 순서로 빌드용 경로를 고릅니다. 사이트가 승인한 스크래치가 자동으로 잡히지 않으면 다음처럼 절대 경로를 지정합니다.

```bash
export KSC_BUILD_SCRATCH=/approved/scratch/path/ksc2026-build
./container/build_kisti_sif.sh
```

이 경로에는 압축을 풀어 작업할 충분한 공간이 필요합니다. 기본 사전 점검 기준은 100 GiB이며, 운영자가 실제 이미지 크기와 사이트 정책을 확인한 뒤 `KSC_MIN_SCRATCH_GIB`로 바꿀 수 있습니다. Apptainer 공식 지침에 따라 fakeroot 빌드의 임시 경로로 NFS를 사용하지 않습니다.

### 대안: 인터넷에 연결된 다른 ARM64 호스트에서 Docker 이미지 만들기

### 사전 조건

- ARM64 Linux 빌드 호스트 또는 ARM64 원격 buildx 빌더
- Docker Engine, Docker buildx
- NGC(`nvcr.io`), Boost 공식 archive와 GitHub 릴리스 압축 파일에 접근할 수 있는 빌드용 인터넷 연결
- NGC 기반 이미지를 내려받을 권한
- 이미지와 압축되지 않은 Docker 이미지 아카이브를 저장할 충분한 공간

저장소 최상위 폴더에서 실행합니다.

```bash
./container/build_image.sh
```

Docker 대안도 KISTI 직접 빌드와 동일하게 기반 이미지의 빌드 도구를 먼저 확인하고, 동일한 URL과 SHA-256으로 Boost.ProgramOptions 정적 라이브러리, OpenBLAS와 nvbandwidth를 빌드합니다. 운영체제의 패키지 관리자로 별도 종속성을 설치하는 우회 경로가 아닙니다.

이 스크립트는 다음을 순서대로 수행합니다.

1. `docker buildx build --platform linux/arm64 --load`
2. 로컬 이미지의 아키텍처 확인
3. GPU 없이 Boost.ProgramOptions의 정적 연결 여부, OpenBLAS/NVPL DGEMM 컴파일·연결·실행, CUDA SM90 대상 컴파일·연결, 강의자료 체크섬을 포함한 기본 동작 점검
4. `docker save`로 `dist/ksc2026-gh200-physicsnemo_25.11-arm64.tar` 아카이브 생성
5. 아카이브의 SHA-256 체크섬 생성

이미지 태그와 Docker 이미지 아카이브 경로를 직접 정할 수도 있습니다.

```bash
./container/build_image.sh \
  ksc2026-gh200-physicsnemo:pilot \
  /srv/ksc2026/ksc2026-gh200-physicsnemo.tar
```

`--load` 뒤 기본 동작 점검을 실행하므로 x86_64 Mac의 기본 로컬 빌드 환경보다 ARM64 원격 빌더나 ARM64 Linux 호스트가 적합합니다.

## 5. 대안 경로: Docker 이미지 아카이브를 SIF로 변환

Docker 대안 경로에서는 Docker 데몬의 이미지를 아카이브로 저장한 뒤 SIF로 변환합니다. SIF 변환 호스트에는 외부 인터넷이 필요하지 않습니다.

```bash
./container/build_sif.sh
```

입력과 출력을 직접 지정하려면 다음과 같이 실행합니다.

```bash
./container/build_sif.sh \
  /srv/ksc2026/ksc2026-gh200-physicsnemo.tar \
  /srv/ksc2026/ksc2026-gh200-physicsnemo.sif
```

스크립트는 저장소의 `Singularity`에 정의한 실행 명령·환경변수·검사 절차를 유지하면서 입력만 `docker-archive`로 바꿉니다. Apptainer가 없고 `singularity` 명령만 있으면 이를 사용합니다. 일반 사용자로 실행하면 `--fakeroot`을 사용하고, 격리된 빌드 컨테이너에서 root 권한으로 실행하면 `--fakeroot` 없이 빌드합니다. 사이트의 사용자 네임스페이스와 fakeroot 허용 정책을 먼저 확인하세요.

같은 태그의 Docker 이미지가 로컬 Docker 데몬에 있다면 직접 변환할 수도 있습니다.

```bash
apptainer build --fakeroot dist/ksc2026.sif Singularity
```

완성된 `.tar`, `.sif`, 각 `.sha256` 파일을 계산 환경으로 옮긴 뒤 전송 전후 체크섬을 비교합니다.

## 6. GH200에서 컨테이너 이미지 검증

### Docker

```bash
docker run --rm --gpus all \
  --entrypoint /opt/nvidia/physicsnemo_env.sh \
  ksc2026-gh200-physicsnemo:25.11-arm64 \
  /opt/ksc2026/container/smoke_test.sh --gpu
```

### Apptainer

```bash
apptainer exec --nv \
  dist/ksc2026-gh200-physicsnemo_25.11-arm64.sif \
  /opt/nvidia/physicsnemo_env.sh \
  /opt/ksc2026/container/smoke_test.sh --gpu
```

`--gpu` 검사는 다음을 확인합니다.

- ARM64 사용자 공간
- 기반 이미지의 빌드 도구, `nvc`, `nvcc`, `nsys`, `nvbandwidth`, JupyterLab
- PhysicsNeMo/PyTorch 불러오기
- NVHPC 25.5, NVPL, Boost.ProgramOptions 정적 라이브러리, OpenBLAS와 고정한 이미지·소스 정보
- 필수 노트북과 실습 이미지
- 제품명이 GH200인 CUDA SM90 GPU와 CUDA 초기화
- 명시적 복사(Explicit copy)·UVM 실행과 짧은 Nsight Systems 보고서 생성
- nvbandwidth 호스트→디바이스·디바이스→호스트 전송 테스트

이 검사는 필수 사전 점검이며 전체 수업의 예행연습을 대체하지 않습니다. `01_GH200`의 컴파일·프로파일링 결과와 `02_PhysicsNeMo`의 PINN·FNO 학습 시간, 최대 GPU 메모리 사용량, 출력 파일을 실제 PILOT GH200에서 별도로 기록해야 합니다.

## 7. 참가자 접속과 실행

### 강의자료를 행사 직전 commit으로 게시

강의자료만 수정한 경우 21GB SIF를 다시 만들지 않습니다. 중앙 운영계정이 인터넷이 되는 로그인 노드에서 정확한 Git commit과 private `site.env`를 지정해 게시합니다.

```bash
/path/to/KSC2026-repo/operations/admin/publish-course.sh \
  --root /scratch/hackathon/ksc2026 \
  --site-env /scratch/<중앙운영계정>/ksc2026-admin/private/site.env \
  --ref main \
  --commit <검증된_40자리_Git_commit>
```

게시가 성공하면 `/scratch/hackathon/ksc2026/course-current`가 정확한 `course-releases/<commit>`을 가리킵니다. 참가자에게는 `course-release.json`의 `participant_paths`에 적힌 강의 파일만 보이고, 운영·컨테이너 빌드 폴더는 작업공간에 복사되지 않습니다. 검증 실패 시 기존 링크는 바뀌지 않습니다. 계산 노드는 이 공유 release만 읽으며 `git`, `curl`, `pip`를 실행하지 않습니다. 행사 중 참가자별 자료가 달라지는 일을 막기 위해 최종 게시 후에는 수업이 끝날 때까지 commit을 고정합니다. 최초 게시와 갱신의 전체 명령은 [`operations/admin/participant/KSC2026-Shared-Launcher-Deployment-Guide.md`](operations/admin/participant/KSC2026-Shared-Launcher-Deployment-Guide.md)를 따릅니다.

### 참가자 로그인과 서버 실행

참가자 PC에 별도의 `.command`나 `.cmd` 파일을 배포하지 않습니다. 중앙 운영자는 `/scratch/hackathon/ksc2026/bin/ksc2026`을 한 번만 배포하며, 계정별 런처나 SIF는 설치하지 않습니다. 참가자는 먼저 PILOT에 일반 SSH로 로그인해 공용 런처를 실행하고, Slurm 배정이 끝난 뒤 화면에 표시되는 터널 명령을 로컬 컴퓨터의 새 터미널에서 실행합니다.

```bash
ssh -o ExitOnForwardFailure=yes -o ServerAliveInterval=30 -o ServerAliveCountMax=3 \
  -N -L 127.0.0.1:8888:<Slurm이 배정한 계산 노드>:<GPU 번호로 정한 Jupyter 포트> \
  <현재 로그인 계정>@<PILOT 로그인 주소>
```

참가자는 SSH 프롬프트에 OTP·비밀번호를 입력하고, PILOT 로그인 후 `/scratch/hackathon/ksc2026/bin/ksc2026`을 실행합니다. 공용 런처는 Slurm에 GH200 한 개를 요청하고, 실제로 배정된 계산 노드와 GPU 번호에서 Jupyter 포트를 정한 뒤 완성된 터널 명령과 `00_Start_Here.ipynb` 주소를 출력합니다. 노트북 수정본과 결과는 `/scratch/<로그인계정>/ksc2026/workspaces/`에, 세션 상태와 로그는 각각 `session/`, `logs/`에 저장됩니다. 원격 서버는 참가자 PC의 브라우저를 직접 열 수 없으므로, 참가자가 출력된 `http://127.0.0.1:8888/...` 주소를 엽니다.

원격 스크립트는 이미 열린 일반 SSH 연결에 PC 쪽 터널을 뒤늦게 추가할 수 없습니다. 따라서 공용 런처가 준비 완료를 알리면 로컬 컴퓨터의 새 터미널에서 출력된 `ssh -N -L ...` 한 줄을 실행하고 그 터미널을 열어 둡니다. SSH·브라우저가 끊겨도 Job은 자동 종료하지 않습니다. PILOT에 다시 로그인해 공용 런처를 실행하면 활성 Job·토큰·작업 폴더를 재사용하고 현재 배정에 맞는 터널 명령을 다시 보여 줍니다. 수업을 완전히 마칠 때만 같은 명령에 `--stop`을 붙여 실행합니다.

현재 확인된 접속 흐름은 다음과 같습니다.

```text
참가자 노트북의 ssh -L → PILOT 로그인 노드 → Slurm으로 배정된 계산 노드 → SIF 안의 JupyterLab
```

OTP·비밀번호·Jupyter 토큰은 저장소, SSH 명령, 참가자 안내문에 저장하지 않습니다. GPU 배정은 정적 `CUDA_VISIBLE_DEVICES`가 아니라 Slurm GRES와 cgroup·device ACL로 보장해야 합니다. GPU partition·GRES 이름, CPU·RAM·24시간 walltime 정책, PILOT 로그인 주소와 로그인 노드에서 계산 노드 Jupyter 포트로의 연결은 행사 전 시험 계정 한 개로 먼저 검증해야 합니다. 강의자료 게시에는 `operations/admin/publish-course.sh`, 공용 런처 배포에는 `operations/admin/participant/install-participants.sh`를 사용합니다.

아래 명령은 운영자가 컨테이너 자체를 세부 점검할 때 사용하는 예시입니다. 참가자는 직접 실행하지 않습니다.

### Docker에서 호스트 작업 폴더 연결

```bash
mkdir -p "$PWD/ksc2026-work"
docker run --rm --gpus all --ipc=host \
  --ulimit memlock=-1 --ulimit stack=67108864 \
  -e KSC_WORKDIR=/work/ksc2026-course \
  -v "$PWD/ksc2026-work:/work/ksc2026-course" \
  -p 8888:8888 \
  ksc2026-gh200-physicsnemo:25.11-arm64
```

### Apptainer에서 쓰기 가능한 작업 폴더 연결

```bash
mkdir -p "$PWD/ksc2026-work"
APPTAINERENV_KSC_WORKDIR=/work/ksc2026-course \
  apptainer run --nv \
  --bind "$PWD/ksc2026-work:/work/ksc2026-course" \
  dist/ksc2026-gh200-physicsnemo_25.11-arm64.sif
```

접속 자동화 스크립트는 실행마다 토큰을 생성합니다. 참가자 컴퓨터 쪽 포트는 `127.0.0.1`에만 열고, 계산 노드 Jupyter는 로그인 노드가 전달할 수 있도록 KISTI 내부 인터페이스 `0.0.0.0:<배정 포트>`에 연결합니다. 참가자는 SSH 터널과 48자리 토큰을 통해서만 접근하며, KISTI 내부 방화벽과 계산 노드 포트 접근 제어를 전제로 합니다.

작업 폴더는 실제 로그인 계정의 `/scratch/<계정>/ksc2026/workspaces/course-<commit>` 아래에 두고, 세션 상태와 로그는 같은 계정의 `session/`, `logs/`에 보존합니다. 공유 SIF와 release는 읽기 전용으로 사용하며 개인 작업 결과를 저장하지 않습니다. `/scratch`의 용량·파일 보존 정책은 행사 전 확인합니다.

## 8. 오프라인 운영 규칙

빌드 단계에서는 NGC 이미지를 받고, 기반 이미지의 빌드 도구를 먼저 확인한 뒤 고정한 Boost·OpenBLAS·nvbandwidth 소스 압축 파일만 내려받아 SHA-256을 확인하고 빌드합니다. KISTI 직접 빌드와 Docker 대안 모두 이 종속성 경로에서 `apt`나 `apt-get`을 사용하지 않습니다. 완성된 이미지를 계산 노드에서 실행한 뒤에는 다음을 금지합니다.

- `apt`/`apt-get` 패키지 설치
- `pip` 패키지 설치
- `git clone`/`git pull`
- `wget`/`curl`로 파일 받기
- Python `requests`, `urllib`, 저수준 소켓(raw socket)을 이용한 외부 파일 받기

이미지는 `PIP_NO_INDEX=1`, `HF_HUB_OFFLINE=1`, `TRANSFORMERS_OFFLINE=1`을 기본값으로 설정합니다. 이 환경변수가 누락된 데이터셋이나 패키지를 대신 만들어 주는 것은 아니므로, 최종 예행연습은 계산 노드의 인터넷을 차단한 상태에서 진행해야 합니다.

## 9. 배포 전 최종 체크리스트

- [ ] KISTI ARM64 호스트에서 기반 이미지의 빌드 도구 사전 검사 성공
- [ ] Boost ProgramOptions·OpenBLAS·nvbandwidth의 고정 URL과 SHA-256 검증 로그 보존
- [ ] KISTI ARM64 호스트의 직접 Apptainer 빌드와 정적 기본 동작 점검 성공
- [ ] SIF의 SHA-256 체크섬을 보관하고, 전송 전후 값이 일치하는지 확인
- [ ] Docker 대안 경로를 사용했다면 ARM64 Docker 빌드, 아카이브와 SIF 체크섬도 확인
- [ ] PILOT GH200에서 공식 PhysicsNeMo 환경 스크립트를 거쳐 `smoke_test.sh --gpu` 성공
- [ ] 필수 동선 `00 → 01_GH200/01 → 01_GH200/02 → 02_PhysicsNeMo/01 → 02_PhysicsNeMo/02`를 빈 작업 폴더에서 완주
- [ ] `nsys` 보고서 생성 및 열람 경로 확인
- [ ] 한 명당 GH200 GPU 한 개 할당과 소규모 동시 시작 부하 확인
- [ ] Slurm이 빈 GPU를 동적으로 배정하고 런처가 실제 노드·GPU·원격 포트를 정확히 출력하는지 확인
- [ ] 로그인 노드에서 배정 계산 노드의 Jupyter 포트로 TCP 접근 가능한지 확인
- [ ] Slurm cgroup·GRES가 각 Job에 GPU 한 개만 보이게 격리하는지 확인
- [ ] Jupyter SSH 포트 포워딩, 로컬 `8888` 충돌 시 즉시 실패, 재접속 동작 확인
- [ ] 영구 작업 경로와 용량 제한 확정
- [ ] NVIDIA NGC/NVHPC/NVPL 포함 SIF의 행사 배포 조건 확인
- [ ] 비공개 GH200 노트북/PPT가 이미지와 공개 저장소에 없음을 재확인
- [ ] `02_PhysicsNeMo/optional`의 FNO 선택 실습이 이미지에 포함되고 필수 동선과 분리되어 표시됨
- [ ] 공식 원본 튜토리얼·챌린지 링크가 현장 실행에 필요하지 않음을 확인

## 10. 공식 참고 문서

- [Apptainer: Building a Container](https://apptainer.org/docs/user/latest/build_a_container.html)
- [Apptainer: Support for Docker and OCI Containers](https://apptainer.org/docs/user/latest/docker_and_oci.html)
- [NVIDIA HPC SDK 25.5 Installation Guide](https://docs.nvidia.com/hpc-sdk/archive/25.5/hpc-sdk-install-guide/index.html)
- [NVIDIA NVPL 25.5 Installation](https://docs.nvidia.com/nvpl/25.5/install.html)
- [Boost 1.83.0 release](https://www.boost.org/releases/1.83.0/)
- [NVIDIA nvbandwidth](https://github.com/NVIDIA/nvbandwidth)
