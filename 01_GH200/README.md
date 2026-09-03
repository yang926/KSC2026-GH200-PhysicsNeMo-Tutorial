# 01_GH200 — Grace CPU와 Hopper GPU 성능 실습

이 모듈은 오전의 GH200 구조 설명을 실제 코드와 측정값으로 확인하는 60분 실습입니다. 참가자는 정해진 예제를 재생하는 데서 끝나지 않고, 컴파일 옵션·CPU 스레드 수·데이터 크기·CUDA 통합 메모리의 이동 정책을 직접 바꿉니다. 모든 실험은 **예상 → 수정 → 실행 → 비교 → 해석** 순서로 진행합니다.

계산 노드에서는 통합 SIF에 들어 있는 도구와 소스만 사용합니다. `apt`, `pip`, `git`, `wget`, `curl`로 무엇을 설치하거나 받지 않습니다.

## 학습 목표

- ARM64 Grace CPU에서 같은 DGEMM 소스를 두 소프트웨어 구성으로 빌드합니다.
- 컴파일 옵션, 행렬 크기와 CPU 스레드 수를 바꾸고 체크섬·실행 시간·GFLOP/s를 비교합니다.
- 명시적 복사, CUDA 통합 메모리, 시스템 할당 메모리의 코드 차이를 설명합니다.
- 통합 메모리의 요구 시 이동과 사전 이동(prefetch)을 Nsight Systems 기록으로 구분합니다.
- 프로그램 전체 결과, Nsight Systems의 API·커널 기록, nvbandwidth의 링크 대역폭을 서로 다른 측정값으로 해석합니다.

## 강의자료와 실습 연결

PPT를 압축하거나 부록으로 옮겨도 연결이 유지되도록 슬라이드 번호 대신 강의자료의 주제로 표시합니다.

| 강의자료 주제 | 핵심 개념 | 노트북에서 확인할 내용 |
|---|---|---|
| Grace–Hopper 결합 구조 | NVLink-C2C, 캐시 일관성, 통합 주소 공간 | 두 메모리의 물리적 위치와 GPU 접근 경로를 먼저 예상 |
| Arm64 소프트웨어 생태계 | ARM64 재컴파일, `-mcpu=native`, NVHPC, NVPL | `01_CPU_Compile_and_Tune.ipynb`에서 실제 빌드 명령과 옵션 수정 |
| CUDA 통합 메모리 | 요구 시 이동, 사전 이동 | `managed.cu`의 `demand`·`prefetch` 모드 비교 |
| CPU·GPU 메모리 접근 방식 | 명시적 복사·통합 메모리·시스템 할당 메모리 | 세 소스의 할당 API와 ATS/HMM 런타임 판정 비교 |
| NVHPC 메모리 모드 | 컴파일러가 제공하는 메모리 추상화 | 이번 실습의 직접적인 CUDA Runtime API 방식과 층위 구분 |
| Nsight Systems | CLI 수집, 비동기 실행, 메모리 활동 | `.nsys-rep`와 CUDA API·커널·메모리 집계표 생성 및 타임라인 해석 |
| nvbandwidth | 메모리 복사 경로의 전송 대역폭 | 호스트→디바이스와 디바이스→호스트 결과 확인 |

## 개념 지도

| 관찰 층위 | Grace CPU 실습 | Hopper GPU 실습 | 판단 근거 |
|---|---|---|---|
| 계산 결과 | 행렬 곱셈 DGEMM | 벡터 덧셈 | 체크섬과 `PASS` |
| 소프트웨어 구성 | GCC+OpenBLAS, `nvc`+NVPL | `nvcc`+CUDA Runtime | 빌드 명령과 실행 파일 |
| 직접 바꾸는 조건 | 컴파일 옵션, 행렬 크기, 스레드 수 | 데이터 크기, 요구 시 이동·사전 이동, 프로파일 대상 | 참가자 설정 셀 |
| 메모리 방식 | CPU 시스템 메모리 | 명시적 복사, CUDA 통합 메모리, 시스템 할당 메모리 | CUDA API와 런타임 속성 |
| 성능 관찰 | 실행 시간, GFLOP/s | CUDA API·커널·메모리 활동, 복사 대역폭 | 결과표, `.nsys-rep`, nvbandwidth |

시스템 할당 메모리는 `new`로 만든 일반 Linux 메모리를 CUDA 커널에 전달하는 세 번째 **할당 방식**입니다. ATS(Address Translation Service)와 HMM(Heterogeneous Memory Management)은 GPU가 이 메모리에 접근할 때 사용할 수 있는 **주소 변환·일관성 경로**이며 별도의 할당 API가 아닙니다. 노트북은 CUDA 런타임 속성을 읽어 실제 지원 여부와 경로를 판정합니다.

## 60분 실습 동선

| 시간 | 참가자 행동 | 비교할 결과 | 완료 기준 |
|---|---|---|---|
| 13:30–13:34 | ARM64·GH200·컴파일러·라이브러리 확인, 결과 예상 작성 | 현재 계산 노드와 SIF 구성 | 필수 도구 `PASS` |
| 13:34–13:40 | 같은 DGEMM을 GCC+OpenBLAS와 `nvc`+NVPL로 빌드 | 실제 컴파일 명령 | 실행 파일 2개 생성 |
| 13:40–13:48 | 컴파일 옵션·행렬 크기·스레드 수를 직접 수정 | 체크섬, 실행 시간, GFLOP/s | 두 결과의 체크섬 일치 |
| 13:48–14:00 | 한 변수만 바꾸는 CPU 스레드 실험 | 스레드 수별 GFLOP/s | 가장 빠른 조건과 이유 기록 |
| 14:00–14:06 | 세 CUDA 소스의 할당·이동 코드를 대조 | `cudaMemcpy`, `cudaMallocManaged`, `new` | 코드 차이 설명 |
| 14:06–14:15 | 데이터 크기와 통합 메모리 모드 수정 | `demand`와 `prefetch`, ATS/HMM 상태 | 지원 경로의 결과 `PASS` |
| 14:15–14:26 | 프로파일 대상을 선택하고 Nsight Systems 실행 | API·커널·메모리 활동 | 선택한 `.nsys-rep` 생성 |
| 14:26–14:30 | nvbandwidth 실행, 관찰 정리 | 양방향 복사 대역폭 | 예상과 측정의 차이 기록 |

## 노트북

1. [`01_CPU_Compile_and_Tune.ipynb`](01_CPU_Compile_and_Tune.ipynb) — 컴파일 옵션, 행렬 크기와 CPU 스레드 수를 바꿔 두 소프트웨어 구성을 비교합니다.
2. [`02_GPU_Memory_Profile.ipynb`](02_GPU_Memory_Profile.ipynb) — CUDA 메모리 방식과 통합 메모리 이동 정책을 바꾸고 Nsight Systems로 기록합니다.

## 생성 파일과 저장 위치

```text
work/gh200/
├── cpu_results_<UTC>.json
├── gpu_results_<UTC>.json
├── bin/
│   ├── dgemm-openblas
│   ├── dgemm-nvpl
│   ├── cuda-explicit
│   ├── cuda-managed
│   └── cuda-system
└── profiles/
    └── <UTC>_<방식>_n<원소수>.nsys-rep
```

실행할 때마다 UTC 시각을 붙인 결과 JSON과 Nsight 보고서를 새로 만들어 이전 측정을 덮어쓰지 않습니다. 생성 파일과 수정한 노트북은 개인 `/scratch` 작업공간에 남습니다. SSH 터널이나 Jupyter 연결이 끊겨도 같은 세션에 다시 접속하면 계속 사용할 수 있습니다. Slurm Job이 끝나면 실행 중이던 커널 상태는 사라지므로, 중요한 설정과 해석은 노트북 셀에 기록하고 `Ctrl-S`로 저장합니다.

## 완료 체크리스트

- [ ] 두 DGEMM 실행 파일을 만들고 체크섬 일치를 확인했습니다.
- [ ] 직접 선택한 컴파일 옵션·행렬 크기·스레드 수와 예상 결과를 기록했습니다.
- [ ] CPU 실험에서 한 번에 한 변수만 바꾸고 결과를 해석했습니다.
- [ ] CUDA 메모리 예제 세 개를 빌드하고 지원되는 경로의 결과를 확인했습니다.
- [ ] `demand`와 `prefetch` 중 프로파일할 대상을 직접 선택했습니다.
- [ ] `.nsys-rep`와 nvbandwidth 결과가 각각 무엇을 측정하는지 설명할 수 있습니다.

지원 소스와 각 파일의 역할은 [`../labs/gh200/README.md`](../labs/gh200/README.md)에 정리되어 있습니다.

[Start Here로 돌아가기](../00_Start_Here.ipynb) · [전체 과정 안내 보기](../README.md) · [다음: 발사체 운동 PINN](../02_PhysicsNeMo/01_Projectile_PINN.ipynb)
