# 노트북 지원 파일 안내

`labs/`는 참가자가 순서대로 실행하는 실습 폴더가 아니라, 번호가 붙은 노트북이 불러오는 **소스 코드·설정·그림**을 모아 둔 곳입니다. 실습은 [`00_Start_Here.ipynb`](../00_Start_Here.ipynb)에서 시작합니다.

```text
labs/
├── gh200/          # DGEMM, CUDA 메모리 예제와 도우미 함수
├── projectile/     # PhysicsNeMo-Sym 발사체 코드·설정·이미지
└── poisson_fno/    # PhysicsNeMo FNO 코드·설정·데이터 생성기·이미지
```

## 노트북과 지원 파일의 연결

| 노트북 | 실행하거나 읽는 파일 | 파일의 역할 |
|---|---|---|
| `01_GH200/01_CPU_Compile_and_Tune.ipynb` | `gh200/blas/dgemm.c`, `gh200/blas/Makefile` | 같은 DGEMM 코드를 OpenBLAS·NVPL 구성으로 빌드 |
| `01_GH200/02_GPU_Memory_Profile.ipynb` | `gh200/cuda_memory/*.cu` | 명시적 복사·통합 메모리·시스템 할당 메모리 예제 |
| `02_PhysicsNeMo/01_Projectile_PINN.ipynb` | `projectile/source_code/`, `projectile/images/` | 발사체 방정식, PhysicsNeMo-Sym 학습 설정과 개념 그림 |
| `02_PhysicsNeMo/02_Poisson_FNO.ipynb` | `poisson_fno/generate_data.py`, `train_fno.py`, `conf/` | Poisson 데이터 생성, FNO 학습·평가와 실행 설정 |
| `02_PhysicsNeMo/optional/FNO_Mode_Ablation.ipynb` | `poisson_fno/`의 같은 학습 코드 | 푸리에 모드 수만 바꾸어 오차와 계산 비용 비교 |

노트북에서 “직접 수정” 단계로 안내한 값과 코드만 바꿉니다. 공통 도우미 함수나 데이터 검증 코드를 임의로 바꾸면 이후 셀의 결과 형식이 달라질 수 있습니다.

## 그림을 읽는 기준

| 그림 | 설명 범위 | 핵심 표기 | 연결되는 코드 |
|---|---|---|---|
| `projectile/images/projectile.svg` | 발사체 문제의 좌표계와 초기속도 | `v₀`, `θ`, 중력 방향, 궤적 | `projectile_eqn.py`의 `x''=0`, `y''=-g` |
| `projectile/images/physicsnemo_sym_workflow.webp` | PhysicsNeMo-Sym에서 문제를 구성해 Solver를 실행하는 전체 절차 | Hydra, Geometry·Dataset, Node, Constraint, Domain, Validator·Inferencer·Monitor, Solver | `projectile.py`의 `run()`과 `conf/config.yaml` |
| `poisson_fno/images/fno_data_flow.svg` | 이 과정의 FNO가 소스항 격자에서 해 격자를 예측하는 모델 내부 흐름 | `f`, lifting, Fourier block, decoder, `u_pred` | `train_fno.py`와 `conf/config_FNO*.yaml` |

PhysicsNeMo-Sym 절차 그림의 점선 상자는 같은 종류의 구성 요소를 여러 개 Domain에 등록할 수 있다는 뜻입니다. `N_c`, `N_v`, `N_i`, `N_m`은 각각 Constraint, Validator, Inferencer, Monitor의 개수입니다. 발사체 실습에서는 Constraint 두 종류와 Validator·Inferencer를 등록하며 Dataset·Monitor 경로는 사용하지 않습니다.

FNO 데이터 흐름 그림에서 주파수 경로는 FFT로 변환한 일부 푸리에 모드에 학습 가능한 가중치를 적용하고, 공간 경로는 각 격자점의 특징을 선형 변환합니다. 두 경로를 더한 결과가 다음 층으로 전달됩니다.

실행 파일, Nsight 보고서, 데이터셋, 체크포인트, 검증 그래프와 평가 지표는 `work/` 또는 각 실습의 `datasets/`, `outputs/` 아래에 생성됩니다. 이 결과 파일은 개인 작업공간에 저장되며 Git 배포 원본에는 포함되지 않습니다.

[GH200 모듈 지도](../01_GH200/README.md) · [PhysicsNeMo 모듈 지도](../02_PhysicsNeMo/README.md) · [전체 과정 안내](../README.md)
