# 01_GH200 — Grace CPU와 Hopper GPU 성능 실습

이 모듈은 같은 계산을 여러 소프트웨어·메모리 구성으로 실행하고, 결과의 정확성과 실행 특성을 측정합니다. 13:30–14:00에는 Grace CPU의 빌드 구성과 스레드 튜닝을, 14:00–14:30에는 Hopper GPU의 메모리 접근과 프로파일링을 다룹니다.

## 학습 목표

- ARM64 GH200와 사전 설치된 컴파일·프로파일링 도구를 확인합니다.
- 같은 DGEMM 소스를 두 소프트웨어 구성으로 빌드하고 체크섬으로 결과를 검증합니다.
- 행렬 크기와 CPU 스레드 수에 따른 실행 시간과 GFLOP/s 변화를 해석합니다.
- 명시적 복사, CUDA 통합 메모리, 시스템 할당 메모리의 실행 기록을 비교합니다.
- 프로그램 전체 실행 시간, Nsight Systems의 API·커널 시간, nvbandwidth의 전송 대역폭을 구분합니다.

## 개념 지도

| 관찰 층위 | Grace CPU 실습 | Hopper GPU 실습 | 확인 근거 |
|---|---|---|---|
| 계산 | 행렬 곱셈 DGEMM | 벡터 덧셈 | 체크섬과 프로그램 출력 |
| 소프트웨어 구성 | GCC+OpenBLAS, `nvc`+NVPL | `nvcc`+CUDA Runtime | 빌드 명령과 실행 파일 |
| 병렬 실행·메모리 | CPU 스레드 수 | 명시적 복사, 통합 메모리, 시스템 할당 메모리 | 측정표와 런타임 속성 |
| 성능 측정 | 실행 시간, GFLOP/s | CUDA API·커널 시간, 전송 대역폭 | 결과표, `.nsys-rep`, nvbandwidth |

시스템 할당 메모리는 `new`로 만든 세 번째 메모리 방식입니다. ATS와 HMM은 GPU가 이 메모리에 접근할 때 선택될 수 있는 일관성 경로이며 별도의 메모리 할당 API가 아닙니다.

## 실습 순서와 완료 기준

| 시간 | 단계 | 실행·관찰 | 완료 기준 | 생성 파일 |
|---|---|---|---|---|
| 13:30–13:35 | [CPU 환경 확인](01_CPU_Compile_and_Tune.ipynb) | ARM64, GH200, GCC, `nvc`, Make 확인 | 필수 도구와 이미지 구성 정보 확인 | 없음 |
| 13:35–13:45 | [두 빌드 구성](01_CPU_Compile_and_Tune.ipynb) | 같은 DGEMM을 OpenBLAS·NVPL에 연결 | 실행 파일 2개 생성 | `work/gh200/bin/dgemm-*` |
| 13:45–14:00 | [정확성·스레드 튜닝](01_CPU_Compile_and_Tune.ipynb) | 체크섬, 행렬 크기, 스레드 수, GFLOP/s 비교 | 체크섬 일치와 성능 변화 기록 | 노트북 결과표 |
| 14:00–14:10 | [GPU 메모리 방식](02_GPU_Memory_Profile.ipynb) | 명시적 복사·통합 메모리·시스템 할당 메모리 실행 | 지원 경로의 결과 일치; 미지원 시 `SKIP` 확인 | `work/gh200/bin/cuda-*` |
| 14:10–14:25 | [Nsight Systems](02_GPU_Memory_Profile.ipynb) | CUDA API, 메모리 작업, 커널 타임라인 수집 | 지원 경로별 보고서 생성 | `work/gh200/profiles/*.nsys-rep` |
| 14:25–14:30 | [nvbandwidth](02_GPU_Memory_Profile.ipynb) | 호스트↔디바이스 복사 대역폭 측정 | 두 방향 측정값 확인 | 노트북 출력 |

## 측정값을 읽는 기준

- **체크섬**은 두 실행 파일이 수치 오차 범위에서 같은 계산 결과를 냈는지 확인합니다.
- **GFLOP/s**는 DGEMM의 부동소수점 연산 처리율을 나타냅니다.
- **프로그램 전체 실행 시간**에는 초기화, 메모리 할당, 복사, 커널 실행과 동기화가 포함됩니다.
- **Nsight Systems**는 CUDA API와 GPU 커널의 실행 순서·시간을 보여 줍니다.
- **nvbandwidth**는 지정한 메모리 복사 경로의 전송 대역폭을 측정합니다.
- `SKIP`은 시스템 할당 메모리의 GPU 직접 접근 기능이 비활성화된 환경에서 표시되는 상태입니다.

## 생성 파일

```text
work/gh200/
├── bin/
│   ├── dgemm-openblas
│   ├── dgemm-nvpl
│   ├── cuda-explicit
│   ├── cuda-managed
│   └── cuda-system
└── profiles/
    └── *.nsys-rep
```

이 파일은 개인 `/scratch` 작업공간에 저장되므로 SSH나 Jupyter 연결 후 다시 접속해도 남아 있습니다.

## 완료 체크리스트

- [ ] 환경 확인에서 ARM64, GH200, 필수 도구, 이미지 구성 정보를 확인했습니다.
- [ ] DGEMM 실행 파일 두 개를 만들고 체크섬 일치를 확인했습니다.
- [ ] 행렬 크기·스레드 수별 결과표에서 가장 빨랐던 조건과 근거를 기록했습니다.
- [ ] CUDA 메모리 예제 세 개를 빌드했습니다. 시스템 할당 메모리가 `SKIP`이면 런타임 속성에서 이유를 확인했습니다.
- [ ] 지원되는 메모리 방식의 `.nsys-rep`를 생성했습니다.
- [ ] nvbandwidth의 호스트→디바이스, 디바이스→호스트 결과를 확인했습니다.

지원 소스와 도우미 함수는 [`../labs/gh200/`](../labs/gh200/README.md)에 있습니다. 노트북의 안내 없이 직접 수정할 필요는 없습니다.

[Start Here로 돌아가기](../00_Start_Here.ipynb) · [전체 과정 안내 보기](../README.md) · [다음: 발사체 운동 PINN](../02_PhysicsNeMo/01_Projectile_PINN.ipynb)
