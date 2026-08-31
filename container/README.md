# 컨테이너 이미지 빌드 기준

이 폴더에는 KSC 2026 통합 강의용 단일 ARM64 실행 이미지를 만드는 운영 파일이 들어 있습니다. 참가자는 이 스크립트를 실행하지 않습니다.

## 현재 검증 상태

Dockerfile, KISTI용 Apptainer 정의 파일, 셸 문법, JSON 구성 정보, 오프라인 실행 경계는 정적으로 검사했습니다. 실제 ARM64 SIF 빌드·PILOT GH200 실행의 상태는 루트 [`Deployment_Guide.MD`](../Deployment_Guide.MD)에서 관리합니다. 실제로 실행해 통과한 단계와 아직 확인이 필요한 단계를 구분해서 기록해야 합니다.

2026-08-28 KISTI ARM64 환경에서 SIF 직접 빌드가 완료되었습니다. 생성된 파일은 21,765,976,064 bytes이며 SHA-256은 `ee43b2c0735b26a7168e53c7e598dd5dc527b1e23284682f790430656d8bdacf`입니다. 아래 세부 버전은 2026-08-30에 이 SHA-256의 SIF를 KISTI PILOT에서 직접 열어 관측한 값입니다. 전체 postbuild 실행 검증 결과는 루트 `Deployment_Guide.MD`와 별도 검증 로그에서 관리합니다.

Dockerfile과 KISTI용 Apptainer 정의 파일은 `nvc`, NVPL, 컴파일러 실행 파일의 누락을 피하기 위해 NVHPC 이미지의 `/opt/nvidia/hpc_sdk` 전체를 복사합니다. 구성이 빠질 위험은 낮지만 최종 Docker 아카이브와 SIF가 커집니다. 실제 크기와 전송 시간을 측정한 뒤 줄여야 한다면, PILOT GH200에서 컴파일·연결·실행 회귀 검사를 유지한 상태로 필요한 하위 경로만 남겨야 합니다.

## 현재 SIF에서 확인한 설치 구성

| 구분 | 확인한 버전·상태 |
|---|---|
| 운영체제·아키텍처 | Ubuntu 24.04.3 LTS · `aarch64` |
| NVIDIA PhysicsNeMo 컨테이너 | Release 25.11 · build 38187082 |
| `nvidia-physicsnemo` | 1.3.0 · git 14e0874 |
| `nvidia-physicsnemo.sym` | 2.3.0 · git a094673 |
| Python | 3.12.3 |
| PyTorch | 2.9.0a0+145a3a7bda.nv25.10 · CUDA 13.0 빌드 |
| NumPy / SciPy / pandas | 1.26.4 / 1.16.2 / 2.3.3 |
| h5py / Hydra / PyYAML | 3.15.1 / 1.3.2 / 6.0.3 |
| Matplotlib / IPython / TensorBoard | 3.10.7 / 9.6.0 / 2.20.0 |
| JupyterLab / Jupyter Server / Notebook | 4.4.9 / 2.17.0 / 7.4.7 |
| CUDA 컴파일러 `nvcc` | 13.0 · build `cuda_13.0.r13.0/compiler.36424714_0` |
| Nsight Systems | 2025.5.1.121 |
| NVIDIA HPC SDK `nvc` | 25.5-0 · Linux ARM64 · `-tp neoverse-v2` |
| NVPL | 25.5 |
| GCC / CMake / GNU Make | 13.3.0 / 3.31.6 / 4.3 |
| OpenBLAS | 0.3.31 |
| nvbandwidth | 0.8 · `/opt/ksc2026/bin/nvbandwidth` |
| Boost.ProgramOptions | 1.83.0 · nvbandwidth에 정적 연결 |

로그인 노드에서 `--nv` 없이 SIF를 열어 버전만 확인하면 NVIDIA 드라이버 연결 경고가 표시될 수 있습니다. 실제 GPU 실습은 Slurm으로 배정된 GH200 계산 노드에서 Apptainer `--nv` 옵션으로 호스트 드라이버를 연결해 실행합니다.

## 빌드 입력의 고정 버전

| 구성 | 버전 | 포함 방식 |
|---|---:|---|
| PhysicsNeMo 기반 이미지 | 25.11 | ARM64 매니페스트 다이제스트로 고정 |
| NVHPC + NVPL | 25.5 | NVIDIA NVHPC ARM64 이미지에서 SDK 전체 복사 |
| Boost.ProgramOptions | 1.83.0 | 공식 소스와 SHA-256 검증 후 정적 라이브러리만 빌드 |
| OpenBLAS | 0.3.31 | 소스 코드 압축 파일의 SHA-256 검증 후 빌드 |
| nvbandwidth | 0.8 | 소스 코드 압축 파일의 SHA-256 검증 후 SM90 대상 빌드 |
| `nvcc`, `nsys`, JupyterLab | 기반 이미지 제공 | 이미지 빌드 중 존재 여부 검사 |

Boost는 `https://archives.boost.io/release/1.83.0/source/boost_1_83_0.tar.gz`와 SHA-256 `c0685b68dd44cc46574cce86c4e17c0f611b15e195be9848dfd0769a0a207628`로 고정합니다. ProgramOptions만 정적 라이브러리로 만들고 BSL-1.0 `LICENSE_1_0.txt`를 이미지의 라이선스 묶음에 보존합니다. OpenBLAS 0.3.31과 nvbandwidth 0.8도 `third-party-sources.json`에 기록한 소스 URL과 SHA-256이 일치한 뒤에만 빌드합니다. NVIDIA 컨테이너와 HPC SDK를 포함한 SIF를 행사 참가자에게 배포할 수 있는 범위는 실제 배포 전에 별도로 확인해야 합니다.

## KISTI 권장 빌드 흐름

KISTI PILOT의 ARM64 로그인 환경에서는 Docker나 Podman을 거치지 않고 Apptainer가 두 NGC ARM64 이미지를 직접 조립합니다. 저장소 최상위 폴더에서 실행합니다.

```bash
module load apptainer/1.4.5
./container/build_kisti_sif.sh
```

`Apptainer.kisti.def`는 NVHPC 단계를 먼저 만들고, PhysicsNeMo 최종 단계로 `/opt/nvidia/hpc_sdk` 전체를 복사합니다. KISTI 직접 빌드는 `apt`나 `apt-get`을 사용하지 않습니다. 대신 최종 기반 이미지에 컴파일러, `make`, CMake, 다운로드·압축 해제·SHA-256 검증 도구가 있는지 먼저 검사하고, 누락 시 소스 다운로드 전에 중단합니다. 그다음 Boost 1.83.0 ProgramOptions 정적 라이브러리, OpenBLAS 0.3.31, nvbandwidth 0.8을 고정한 소스와 SHA-256으로 최대 12개 작업을 사용해 빌드합니다. SIF 압축 작업도 같은 상한을 적용합니다. 참가자 강의자료와 `operations/`는 파일별 허용 목록으로 복사하므로, 실제 `site.env`, 계정 매핑, 계정별 SSH 안내문과 운영 생성물은 SIF에 들어가지 않습니다.

`build_kisti_sif.sh`는 `KSC_BUILD_SCRATCH`, 사이트의 `SCRATCH`, 사용자별 `/tmp` 순서로 빌드용 경로를 고르고 그 아래에 Apptainer 캐시와 임시 파일을 둡니다. NFS 임시 경로는 거부합니다. 자동으로 고른 위치 대신 사이트가 승인한 스크래치를 쓰려면 `KSC_BUILD_SCRATCH=/absolute/path`를 지정합니다. SIF를 만든 뒤 정적 기본 동작 점검과 SHA-256 검사를 마치고, 실제 GH200에서 실행할 `--gpu` 검사 명령을 출력합니다.

## Docker가 이미 있는 환경의 대안 흐름

인터넷과 NGC에 접근할 수 있는 별도 ARM64 Docker 빌드 호스트에서는 기존 흐름도 사용할 수 있습니다. Docker 대안 역시 기반 이미지의 빌드 도구를 먼저 확인하고, KISTI 직접 빌드와 동일한 Boost·OpenBLAS·nvbandwidth 소스 URL과 SHA-256을 사용합니다. 운영체제의 패키지 관리자로 Boost나 다른 빌드 종속성을 설치하는 별도 경로가 아닙니다.

```bash
./container/build_image.sh
./container/build_sif.sh
```

첫 번째 스크립트는 `linux/arm64` Docker 이미지를 로컬 데몬에 만들고 정적 사전 점검을 마친 뒤 `dist/*.tar`로 내보냅니다. 두 번째 스크립트는 그 Docker 아카이브를 입력으로 사용해 내용이 같은 SIF를 만듭니다. 경로를 바꾸려면 각 스크립트의 첫째·둘째 인자를 사용합니다.

```bash
./container/build_image.sh my-registry/ksc2026:pilot /srv/images/ksc2026.tar
./container/build_sif.sh /srv/images/ksc2026.tar /srv/images/ksc2026.sif
```

로컬 Docker 데몬에서 직접 SIF를 만들 때는 저장소 최상위 폴더에서 다음 명령을 사용할 수도 있습니다. 이때 `Singularity`의 `From:` 태그와 로컬 데몬의 태그가 같아야 합니다.

```bash
apptainer build --fakeroot dist/ksc2026.sif Singularity
```

## 실행 계약

- 고정 런타임: 검증된 ARM64 SIF와 SHA-256
- 이미지 내 강의자료: `/opt/ksc2026/course-source`의 빌드 시점 비상용 사본
- 정상 강의자료: 관리자가 GitHub `main`의 검증된 commit을 읽기 전용 release로 게시하고, 모든 사용자가 같은 release를 사용
- 참가자 작업 폴더: 두 경로 모두 `course-release.json`의 `participant_paths`만 개인 `/scratch` 아래 commit별 쓰기 가능한 폴더로 준비
- 컨테이너 작업 경로: 참가자 작업 폴더를 SIF의 `/workspace`에 읽기·쓰기 가능하게 연결
- 같은 commit 재접속: 기존 파일과 결과를 보존
- 새 commit 게시: 새 작업 폴더를 만들고 이전 작업을 덮어쓰지 않음
- 오프라인 보호 환경변수: `PIP_NO_INDEX=1`, `HF_HUB_OFFLINE=1`, `TRANSFORMERS_OFFLINE=1`
- 실행 중 패키지 설치·파일 받기: 없음
- Docker와 SIF 시작 명령: PhysicsNeMo 공식 `/opt/nvidia/physicsnemo_env.sh`를 거쳐 KSC 시작 스크립트 실행
- 접속 자동화: `KSC_JUPYTER_IP`, `KSC_JUPYTER_PORT`, `KSC_JUPYTER_TOKEN`, `KSC_WORKDIR` 반영
- 포트 충돌 처리: 지정 포트만 사용하고 `ServerApp.port_retries=0`으로 다른 포트 자동 이동 금지

GPU 없이 강의자료와 개발 도구만 검사하려면 `smoke_test.sh --static`, 실제 GH200 연결까지 검사하려면 `--gpu`를 사용합니다. 정적 검사는 파일 존재 여부뿐 아니라 Boost.ProgramOptions의 정적 연결 여부, 작은 DGEMM의 OpenBLAS·NVPL 컴파일·연결·실행, CUDA 예제 세 개의 SM90 대상 컴파일·연결과 강의자료 체크섬을 검증합니다. `--gpu`는 제품명이 GH200인지 확인하고 명시적 복사(Explicit copy)와 UVM 실행, 짧은 Nsight Systems 보고서 생성, nvbandwidth 전송 테스트까지 수행합니다.
