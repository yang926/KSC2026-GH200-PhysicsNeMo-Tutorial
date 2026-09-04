<h1 align="center">KSC 2026 · GH200 × PhysicsNeMo 통합 실습</h1>

<p align="center"><strong>Grace CPU와 Hopper GPU의 실행 특성을 측정하고, PhysicsNeMo로 PINN과 푸리에 신경 연산자(Fourier Neural Operator, FNO)를 구현합니다.</strong></p>

<p align="center">한국어 과정 · 참가자 1명당 GH200 1대 · 계산 노드 오프라인 실행</p>

<h2 align="center"><a href="00_Start_Here.ipynb">00 Start Here — 환경 점검 시작 →</a></h2>

<p align="center"><a href="#행사-당일-jupyterlab-접속">접속·재접속 안내</a> · <a href="#과정-개요">전체 과정 구성</a></p>

<p align="center"><a href="01_GH200/README.md">01 GH200 모듈 지도</a> · <a href="02_PhysicsNeMo/README.md">02 PhysicsNeMo 모듈 지도</a></p>

---

이 문서는 JupyterLab에 접속하면 가장 먼저 열리는 과정 안내서입니다. 전체 개념·실습 순서·완료 기준을 확인한 뒤 상단의 **00 Start Here — 환경 점검 시작**을 눌러 실행 환경을 점검합니다.

## 행사 당일 JupyterLab 접속

강의 슬라이드(PPT)에 안내된 PILOT SSH 명령으로 로그인한 뒤 공용 명령을 실행하면, Slurm이 현재 사용 가능한 계산 노드의 NVIDIA GH200 한 개를 배정합니다. 참가자 컴퓨터에서 로컬 터미널 두 개와 웹 브라우저를 사용합니다.

1. **로컬 터미널 1**에서 강의 슬라이드(PPT)에 안내된 PILOT SSH 명령을 실행하고 OTP와 비밀번호를 입력합니다.
2. PILOT 로그인 노드에 접속되면 다음 한 줄을 실행합니다.

   ```bash
   /scratch/hackathon/ksc2026/bin/ksc2026
   ```

3. `KSC 2026 JupyterLab 준비 완료`가 표시되면 배정된 계산 노드와 GH200 한 개를 확인합니다.
4. **로컬 터미널 2**를 새로 열고, 화면의 `[1/2]` 아래에 표시된 `ssh -N ...` 한 줄을 통째로 붙여 넣습니다. OTP와 비밀번호를 입력한 뒤 화면이 멈춰 있으면 정상입니다. 이 터미널은 실습 중 열어 둡니다.
5. 화면의 `[2/2]` 아래에 표시된 주소를 웹 브라우저에서 엽니다. 이 README 안내서가 렌더링된 첫 화면으로 열립니다. 상단의 **00 Start Here — 환경 점검 시작**을 누릅니다. 주소에 포함된 개인 접속 토큰은 다른 사람과 공유하지 않습니다.

### 저장과 재접속

- 노트북은 60초마다 자동 저장됩니다. 중요한 변경 뒤에는 macOS에서 `Cmd+S`, Windows·Linux에서 `Ctrl+S`를 누릅니다.
- 파일은 `/scratch/<계정>/ksc2026/workspaces/`에 저장되며 SSH 연결이나 Slurm Job이 끝나도 남습니다.
- 브라우저만 닫았다면 같은 주소를 다시 엽니다.
- 터미널 2의 터널이 끊겼다면 터미널 1에서 공용 명령을 다시 실행하고, 다시 표시된 `ssh -N ...` 명령을 새 로컬 터미널에서 실행합니다.
- PILOT 로그인까지 끊겼다면 강의 슬라이드(PPT)에 안내된 SSH 명령으로 다시 로그인한 뒤 공용 명령을 실행합니다.
- 활성 Job이 남아 있으면 같은 Job과 작업공간으로 돌아갑니다. Job이 끝난 경우에도 저장 파일은 남지만 Python 변수, GPU 메모리와 실행 중이던 셀은 사라집니다.

### 기억할 명령 세 개

```bash
# 시작 또는 기존 세션 재접속
/scratch/hackathon/ksc2026/bin/ksc2026

# 운영자가 게시한 최신 강의자료를 새 작업공간에 준비
/scratch/hackathon/ksc2026/bin/ksc2026 --refresh

# 현재 계정의 Slurm Job 종료 — 저장 파일은 유지
/scratch/hackathon/ksc2026/bin/ksc2026 --stop
```

최신 강의자료로 바꿀 때는 먼저 파일을 저장하고 `--stop`을 실행한 뒤 `--refresh`를 실행합니다. 이전 작업공간은 삭제하거나 덮어쓰지 않습니다.

`--refresh`는 GitHub에 직접 접속하지 않고, 중앙 운영자가 검증해 게시한 최신 강의자료를 새 개인 작업공간에 복사합니다. GitHub `main`의 변경은 중앙 운영자가 게시한 뒤에 참가자에게 제공됩니다.

## 과정 개요

전체 과정은 환경 점검, GH200 시스템 실습, PhysicsNeMo 물리 AI 실습 순서로 진행합니다.

| 시간 | 세션 | 사용하는 자료 | 핵심 결과 |
|---|---|---|---|
| 11:00–12:00 | GH200 소개 | 현장 강의 슬라이드 | Grace CPU, Hopper GPU, CPU·GPU 일관성 메모리 구조 이해 |
| 13:30–14:00 | Grace CPU 컴파일·튜닝 | [`01_CPU_Compile_and_Tune.ipynb`](01_GH200/01_CPU_Compile_and_Tune.ipynb) | OpenBLAS·NVPL 빌드, 정확성 확인, 스레드별 성능표 |
| 14:00–14:30 | Hopper GPU 메모리·프로파일링 | [`02_GPU_Memory_Profile.ipynb`](01_GH200/02_GPU_Memory_Profile.ipynb) | CUDA 메모리 경로, Nsight Systems 보고서, 전송 대역폭 |
| 14:40–16:00 | PhysicsNeMo 기본/PINN | [`01_Projectile_PINN.ipynb`](02_PhysicsNeMo/01_Projectile_PINN.ipynb) | 발사체 궤적 예측, 검증 오차, 결과 그래프 |
| 16:10–17:30 | 신경 연산자/FNO | [`02_Poisson_FNO.ipynb`](02_PhysicsNeMo/02_Poisson_FNO.ipynb) | Poisson 해 예측, 테스트 오차, 실행 시간·메모리 기록 |
| 조기 완료 | FNO 푸리에 모드 비교 | [`FNO_Mode_Ablation.ipynb`](02_PhysicsNeMo/optional/FNO_Mode_Ablation.ipynb) | 모드 6개·12개 설정의 오차와 계산 비용 비교 |

## 학습 목표

과정을 마치면 다음 내용을 설명하고 직접 확인할 수 있습니다.

1. Grace CPU에서 컴파일러·수학 라이브러리·스레드 수가 계산 실행에 미치는 영향을 측정합니다.
2. Hopper GPU의 명시적 복사, CUDA 통합 메모리, 시스템 할당 메모리 경로를 실행 기록으로 비교합니다.
3. PhysicsNeMo-Sym의 `Node`, `Constraint`, `Domain`, `Validator`, `Inferencer`, `Solver`가 학습 과정에서 맡는 역할을 찾습니다.
4. PINN이 초기조건과 미분방정식 잔차를 손실값으로 사용하는 원리를 설명합니다.
5. FNO가 소스항을 주파수 성분으로 처리하고 새로운 소스항에 대응하는 해를 예측하는 과정을 설명합니다.
6. 실행 시간, 메모리 사용량, 상대 L2 오차와 시각화 결과를 근거로 실험 결과를 해석합니다.

## 전체 실습 지도

| 순서 | 수행할 실험 | 사용하는 도구 | 생성되는 결과 | 완료 기준 |
|---:|---|---|---|---|
| 0 | ARM64·GH200·실행 환경 확인 | Python, CUDA, Jupyter | 환경 점검 출력 | 필수 항목이 모두 `READY` |
| 1-1 | 같은 DGEMM을 두 빌드 구성으로 실행 | GCC, `nvc`, OpenBLAS, NVPL | 실행 파일 2개, 체크섬, GFLOP/s 표 | 두 결과의 체크섬 일치와 성능 변화 설명 |
| 1-2 | 세 메모리 방식의 실행 경로 비교 | CUDA, Nsight Systems, nvbandwidth | CUDA 실행 파일, `.nsys-rep`, 대역폭 결과 | 데이터 이동과 측정 지표의 차이 설명 |
| 2-1 | 초기조건과 ODE 잔차로 궤적 학습 | PhysicsNeMo-Sym, PyTorch | 체크포인트, `validator.npz`, `inferencer_data.npz`, 예측 그래프 | 학습 구간과 외삽 구간의 오차 해석 |
| 2-2 | 여러 소스항에 대응하는 Poisson 해 학습 | PhysicsNeMo FNO, PyTorch | metrics JSON, 테스트 예측 그림 | 처음 보는 소스항의 오차·시간·메모리 해석 |
| 선택 | FNO 푸리에 모드 수 변경 | PhysicsNeMo FNO | 설정별 metrics, 비교표·그래프 | 모드 수에 따른 오차와 계산 비용 비교 |

## 01_GH200 — Grace CPU와 Hopper GPU 성능 실습

### Grace CPU: 컴파일과 스레드 튜닝

같은 DGEMM 소스 코드를 다음 두 소프트웨어 구성으로 빌드합니다.

- GCC + OpenBLAS 0.3.31
- NVIDIA HPC SDK `nvc` + NVPL 25.5

두 실행 파일의 체크섬으로 계산 결과를 확인한 뒤 행렬 크기와 CPU 스레드 수를 바꾸어 실행 시간을 측정합니다. 이 실험은 컴파일러와 BLAS 라이브러리 조합을 함께 비교하므로 결과는 **빌드 구성별 성능**으로 해석합니다.

### Hopper GPU: 메모리 경로와 프로파일링

벡터 덧셈을 세 가지 메모리 방식으로 실행합니다.

- 명시적 호스트↔디바이스 복사(`cudaMalloc` + `cudaMemcpy`)
- CUDA 통합 메모리(`cudaMallocManaged`)
- 시스템 할당 메모리(`new`)

시스템 할당 메모리는 세 번째 할당 방식입니다. ATS와 HMM은 GPU가 이 메모리에 접근할 때 사용할 수 있는 일관성 경로이며 별도의 메모리 할당 API가 아닙니다. `SKIP`은 해당 GPU·드라이버 환경에서 시스템 할당 메모리 접근 경로를 사용할 수 없음을 나타냅니다.

Nsight Systems에서는 CUDA API·메모리 작업·커널 실행 순서를 확인하고, nvbandwidth에서는 호스트↔디바이스 복사 대역폭을 측정합니다.

[01_GH200 상세 모듈 지도 →](01_GH200/README.md)

## 02_PhysicsNeMo — PINN과 FNO로 물리 방정식 풀기

### 발사체 운동 PINN

발사체 PINN은 정답 궤적을 가중치 업데이트에 사용하지 않습니다. 해석해는 학습 중 정기 검증과 학습 종료 후 정확도 확인에 사용합니다. 학습 손실에는 다음 초기조건과 운동방정식의 잔차가 들어갑니다.

$$
x(0)=0, \quad y(0)=0, \quad
x'(0)=v_0\cos\theta, \quad y'(0)=v_0\sin\theta
$$

$$
x''(t)=0, \qquad y''(t)=-g
$$

실습 설정은 `v₀=40 m/s`, `θ=60°`, `g=9.81 m/s²`입니다. 방정식 잔차는 신경망의 예측값을 운동방정식에 대입했을 때 남는 오차입니다.

### Poisson FNO

FNO 실습에서는 공간마다 주어진 소스항 `f(x,y)`와 그에 대응하는 Poisson 해 `u(x,y)`의 예를 학습합니다. 학습을 마치면 새로운 소스항 전체를 입력받아 격자 전체의 해를 예측합니다.

| 구분 | 발사체 PINN | Poisson FNO |
|---|---|---|
| 입력 | 시간 `t` | 격자 위 소스항 `f(x,y)` |
| 출력 | 고정된 초기조건의 궤적 `x(t), y(t)` | 소스항에 대응하는 해 `u(x,y)` |
| 학습 신호 | 초기조건 + ODE 잔차 | 여러 소스항·해의 쌍 `(f,u)` |
| 평가 | 해석해와 궤적 비교 | 학습에 사용하지 않은 소스항의 해와 비교 |

FNO는 공간 패턴을 주파수별 성분으로 표현하고, 선택한 푸리에 성분에 학습 가능한 가중치를 적용합니다. 자세한 PhysicsNeMo-Sym 구성과 FNO 데이터 흐름은 모듈 안내에서 코드와 함께 설명합니다.

[02_PhysicsNeMo 상세 모듈 지도 →](02_PhysicsNeMo/README.md)

## 실습 환경

### Jupyter와 교육용 컨테이너의 동작 방식

```text
참가자 컴퓨터의 브라우저
        │  SSH 터널
        ▼
PILOT 로그인 노드의 공용 런처
        │  Slurm Job 제출
        ▼
배정된 GH200 계산 노드 ── Apptainer로 교육용 SIF 실행
        │                    ├─ JupyterLab·Python
        │                    ├─ PhysicsNeMo·PyTorch
        │                    └─ 컴파일러·프로파일러
        ▼
개인 /scratch 작업공간을 연결해 노트북과 결과 저장
```

SIF(Singularity Image Format)는 Apptainer가 실행하는 단일 컨테이너 이미지 파일입니다. 소프트웨어는 중앙 SIF에서 실행하고, 참가자가 수정한 노트북과 결과만 개인 `/scratch` 작업공간에 저장합니다. 따라서 행사 중에는 PhysicsNeMo를 설치하지 않고 Python에서 다음 모듈을 바로 불러옵니다.

```python
import physicsnemo
import physicsnemo.sym
```

행사 중에는 계산 노드가 오프라인이므로 `pip install`을 실행하지 않습니다.

### 행사 후 개인 환경에서 PhysicsNeMo 사용

개인 환경이 [PhysicsNeMo 시스템 요구사항](https://docs.nvidia.com/physicsnemo/latest/getting-started/system_requirements.html)을 만족한다면 Python 가상환경에 최신 패키지를 설치할 수 있습니다. 아래 명령은 기본·CPU 검증용입니다.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install "nvidia-physicsnemo[sym]"
```

NVIDIA GPU를 사용하는 새 환경에서는 위 명령을 그대로 복사하기 전에 [공식 설치 안내](https://docs.nvidia.com/physicsnemo/latest/getting-started/installation.html)의 호환표에서 PyTorch와 CUDA 조합을 확인합니다. 문서가 안내하는 환경에 맞춰 `cu12` 또는 `cu13` extra를 `sym`과 함께 선택하거나, 호환되는 PyTorch를 먼저 설치합니다. 운영체제·드라이버·CUDA 버전에 관계없이 통하는 단일 GPU 설치 명령은 없습니다.

설치 뒤에는 패키지 이름이 아니라 다음 import 이름으로 확인합니다.

```python
from importlib.metadata import version
import torch
import physicsnemo
import physicsnemo.sym

print("PhysicsNeMo:", version("nvidia-physicsnemo"))
print("CUDA 사용 가능:", torch.cuda.is_available())
```

`torch.cuda.is_available()`이 `False`이면 PhysicsNeMo import 성공과 별개로 NVIDIA 드라이버·CUDA가 연결된 실행 환경인지 확인해야 합니다. 설치 가능한 Python·PyTorch·CUDA 조합은 [공식 설치 안내](https://docs.nvidia.com/physicsnemo/latest/getting-started/installation.html)를 우선합니다.

이 과정의 노트북은 고정된 **PhysicsNeMo 25.11 SIF**를 기준으로 작성했습니다. 최신 PhysicsNeMo v2.0에서는 API 구성이 달라졌으므로 기존 `Solver`·`Domain`·`Constraint` 코드를 그대로 실행하기보다 [v2.0 migration guide](https://github.com/NVIDIA/physicsnemo/blob/main/v2.0-MIGRATION-GUIDE.md)와 최신 예제를 기준으로 옮깁니다. 행사와 같은 25.11 환경을 정확히 재현해야 할 때만 공식 25.11 컨테이너를 선택하면 됩니다. 일반적인 새 프로젝트에서 컨테이너 사용은 필수가 아닙니다.

### 검증된 이미지 구성

아래 버전은 SHA-256이 `ee43b2c0735b26a7168e53c7e598dd5dc527b1e23284682f790430656d8bdacf`인 ARM64 SIF를 2026년 8월 30일 KISTI PILOT에서 검증한 결과입니다.

| 구성 | 설치 버전 | 실습에서 사용하는 기능 |
|---|---|---|
| 운영체제·아키텍처 | Ubuntu 24.04.3 LTS · `aarch64` | GH200 계산 노드 실행 기반 |
| NVIDIA PhysicsNeMo 컨테이너 | Release 25.11 | 통합 실행 환경 |
| PhysicsNeMo / PhysicsNeMo-Sym | 1.3.0 / 2.3.0 | FNO 모델, PINN 문제 구성·학습 |
| Python | 3.12.3 | 모든 노트북과 학습 코드 |
| PyTorch | 2.9.0a0+145a3a7bda.nv25.10 · CUDA 13.0 빌드 | GPU 학습·추론 |
| CUDA 컴파일러 | 13.0 | GH200 CUDA 예제 빌드 |
| Nsight Systems | 2025.5.1 | CUDA API·커널 타임라인 수집 |
| NVIDIA HPC SDK / NVPL | 25.5 / 25.5 | Grace CPU 컴파일, BLAS 계산 |
| GCC / CMake / GNU Make | 13.3.0 / 3.31.6 / 4.3 | C·CUDA 예제 빌드 |
| OpenBLAS | 0.3.31 | Grace CPU DGEMM 비교 |
| nvbandwidth | 0.8 | GH200 메모리 전송 대역폭 측정 |
| Boost.ProgramOptions | 1.83.0, nvbandwidth에 정적 연결 | nvbandwidth 실행 의존성 |
| JupyterLab / Jupyter Server / Notebook | 4.4.9 / 2.17.0 / 7.4.7 | SSH 터널을 통한 노트북 실행 |
| NumPy / SciPy / pandas | 1.26.4 / 1.16.2 / 2.3.3 | 데이터 생성·수치 계산·결과 분석 |
| h5py / Hydra / PyYAML | 3.15.1 / 1.3.2 / 6.0.3 | 데이터셋·실행 설정 관리 |
| Matplotlib / IPython / TensorBoard | 3.10.7 / 9.6.0 / 2.20.0 | 시각화·대화형 실행·학습 기록 확인 |

현재 SIF 파일은 21,765,976,064 bytes이며 SHA-256은 `ee43b2c0735b26a7168e53c7e598dd5dc527b1e23284682f790430656d8bdacf`입니다. 계산 노드에서는 패키지를 설치하거나 저장소를 내려받지 않습니다.

## 참가자 작업공간

```text
.
├── README.md
├── 00_Start_Here.ipynb
├── 01_GH200/
│   ├── README.md
│   ├── 01_CPU_Compile_and_Tune.ipynb
│   └── 02_GPU_Memory_Profile.ipynb
├── 02_PhysicsNeMo/
│   ├── README.md
│   ├── 01_Projectile_PINN.ipynb
│   ├── 02_Poisson_FNO.ipynb
│   └── optional/
├── labs/                    # 소스 코드·설정·강의 이미지
├── work/                    # GH200 실습 실행 후 생성
├── LICENSE
├── PROVENANCE.md
└── course-release.json
```

[`labs/`](labs/README.md)는 노트북이 호출하는 지원 파일입니다. 노트북에서 직접 수정하도록 안내한 부분만 바꿉니다. `work/`와 각 PhysicsNeMo 실습의 `outputs/`는 실행 중 생성되며 재접속 후에도 남습니다.

## 추가 학습 자료

필수 FNO 실습을 일찍 마친 참가자는 진행자 안내에 따라 [FNO 푸리에 모드 수 비교](02_PhysicsNeMo/optional/README.md)를 진행할 수 있습니다.

- [OpenHackathons AI-Powered-Physics-Bootcamp](https://github.com/openhackathons-org/AI-Powered-Physics-Bootcamp)
- [원본 튜토리얼 모음](https://github.com/openhackathons-org/AI-Powered-Physics-Bootcamp/tree/main/tutorial)
- [원본 챌린지 모음](https://github.com/openhackathons-org/AI-Powered-Physics-Bootcamp/tree/main/challenge)

## 출처와 라이선스

PhysicsNeMo 과정은 공개 [OpenHackathons AI-Powered-Physics-Bootcamp](https://github.com/openhackathons-org/AI-Powered-Physics-Bootcamp)를 KSC 2026에 맞게 개작했습니다. 세부 출처와 재배포 경계는 [`PROVENANCE.md`](PROVENANCE.md)에 기록합니다.

저장소 루트 [`LICENSE`](LICENSE)는 Apache License 2.0입니다. 원본에서 가져온 자료와 제3자 구성 요소에는 각각의 라이선스와 고지가 우선 적용됩니다.

## 접속 및 운영 문서

### 사용자

- 공용 명령의 사용·저장·재접속: [온라인 사용자 실행 안내](https://github.com/yang926/KSC2026-GH200-PhysicsNeMo-Tutorial/blob/main/operations/participant/README.md)
- 행사 전 시험 계정 접속·저장·재접속 점검: [온라인 파일럿 검증 안내](https://github.com/yang926/KSC2026-GH200-PhysicsNeMo-Tutorial/blob/main/operations/KSC2026-Pilot-Validation-Guide.md)

### 중앙 환경 운영자

행사 공용 `/scratch/hackathon/ksc2026/bin/ksc2026` 배포 순서는 [온라인 공용 런처 배포 매뉴얼](https://github.com/yang926/KSC2026-GH200-PhysicsNeMo-Tutorial/blob/main/operations/admin/participant/KSC2026-Shared-Launcher-Deployment-Guide.md)을 사용합니다. 중앙 owner는 `sudo` 없이 운영하며, 기존 배포의 갱신·복구는 [상세 운영 매뉴얼](https://github.com/yang926/KSC2026-GH200-PhysicsNeMo-Tutorial/blob/main/operations/admin/participant/KSC2026-Admin-Deployment-Guide.md)을 따릅니다.

강의자료만 바뀌었다면 GitHub `main`에 push한 뒤 PILOT 로그인 노드에서 중앙 owner가 `/scratch/hackathon/ksc2026/admin/bin/refresh-course`를 한 번 실행합니다. GitHub push만으로 중앙 게시본이 자동 변경되지는 않습니다.
