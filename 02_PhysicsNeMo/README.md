# 02_PhysicsNeMo — 물리식을 이용한 학습과 신경 연산자

이 모듈은 PhysicsNeMo-Sym으로 서로 다른 두 학습 문제를 구성합니다. 첫 실습에서는 초기속도와 발사각이 고정된 발사체의 시간별 위치를 물리식으로 학습합니다. 두 번째 실습에서는 여러 소스항과 해의 예를 학습한 뒤, 새로운 소스항에 대응하는 전체 해를 예측합니다.

## 학습 목표

- 신경망 예측값을 운동방정식에 넣었을 때 남는 오차인 **방정식 잔차**가 PINN의 학습 손실이 되는 원리를 설명합니다.
- PhysicsNeMo-Sym의 `Node`, `Constraint`, `Domain`, `Validator`, `Inferencer`, `Solver`를 실제 코드에서 찾습니다.
- FNO가 FFT로 공간 패턴을 주파수 성분으로 나누고, 선택한 성분을 학습해 해를 예측하는 과정을 설명합니다.
- 별도 테스트 데이터의 오차와 실행 시간·GPU 메모리 측정값을 해석합니다.

## 모듈 지도

| 세션 | 단계 | 핵심 개념 | 실행 결과 | 완료 기준 |
|---|---|---|---|---|
| 14:40–16:00 | [02-1 발사체 운동 PINN](01_Projectile_PINN.ipynb) | 초기조건, ODE 잔차, PhysicsNeMo-Sym 학습 구성 | `validator.npz`, 상대 L2·최대 절대 오차, 궤적 그래프 | 학습 성공 후 해석해와 PINN 예측 비교 |
| 16:10–17:30 | [02-2 Poisson FNO](02_Poisson_FNO.ipynb) | 연산자 학습, 푸리에 변환 블록, 지도학습 | 테스트 지표 JSON, 입력·정답·예측·오차 그림 | 별도 테스트 데이터의 오차와 자원 사용량 확인 |
| 조기 완료 | [FNO 모드 수 비교](optional/FNO_Mode_Ablation.ipynb) | 모델 용량과 계산 비용의 균형 | 모드 6개·12개 비교표와 그래프 | 두 설정의 오차·시간·메모리 차이 설명 |

## PINN에서 FNO로

| 구분 | 발사체 운동 PINN | Poisson FNO |
|---|---|---|
| 입력 | 시간 `t` | 격자에 주어진 소스항 `f(x,y)` |
| 출력 | 위치 `x(t), y(t)` | 격자 전체의 해 `u(x,y)` |
| 학습 자료 | 네 개의 초기조건과 운동방정식 | 여러 소스항과 정답 해의 쌍 `(f,u)` |
| 학습 후 사용 | 고정된 초기조건에서 시간별 궤적 계산 | 처음 보는 소스항에 대응하는 해 예측 |
| 평가 | 해석해와 궤적 오차 비교 | 별도 테스트 데이터에서 예측 오차 계산 |

## PhysicsNeMo-Sym 학습 구성

<p align="center"><img src="../labs/projectile/images/physicsnemo_sym_workflow.webp" width="900" alt="PhysicsNeMo-Sym에서 문제를 구성하고 학습을 실행하는 절차" /></p>

<p align="center"><em>그림 1. PhysicsNeMo-Sym의 학습 구성 절차. 설정과 방정식·모델을 준비하고, 학습·검증·추론 구성 요소를 Domain에 등록한 뒤 Solver로 학습을 실행합니다.</em></p>

| 구성 단계 | 발사체 PINN 코드 |
|---|---|
| Hydra 설정 | `labs/projectile/source_code/conf/config.yaml` |
| 방정식·신경망 노드 | `ProjectileEquation` + `instantiate_arch()` |
| 학습 조건 | `initial_condition`, `ode_constraint` |
| Domain | `projectile_domain` |
| 평가·추론 | `validator`, `grid_inference` |
| 학습 실행 | `Solver(...).solve()` |

`N_c`, `N_v`, `N_i`, `N_m`은 Domain에 등록한 Constraint, Validator, Inferencer, Monitor의 개수를 나타냅니다. 발사체 실습은 Dataset 입력과 Monitor를 사용하지 않습니다.

출처: [NVIDIA PhysicsNeMo-Sym User Guide — PINNs Tutorials](https://docs.nvidia.com/physicsnemo/25.11/user-guide/pinns-tutorials/index.html)

## FNO 데이터 흐름

<p align="center"><img src="../labs/poisson_fno/images/fno_data_flow.svg" width="980" alt="소스항을 특징 채널로 바꾸고 푸리에 변환 블록을 거쳐 해를 예측하는 FNO 데이터 흐름" /></p>

<p align="center"><em>그림 2. 소스항 `f`를 특징 채널로 확장한 뒤 여러 푸리에 변환 블록을 거쳐 예측 해 `u_pred`를 출력합니다. 각 블록은 주파수 경로와 공간 영역 선형 경로를 합칩니다.</em></p>

1. 특징 채널 변환(lifting)이 소스항 `f(x,y)`를 여러 내부 특징 채널로 확장합니다.
2. FFT가 공간 패턴을 주파수별 성분으로 표현합니다.
3. 각 층은 선택한 푸리에 모드에 학습 가능한 가중치를 적용하고 역 FFT를 수행합니다.
4. 주파수 경로와 공간 영역의 선형 경로를 더한 뒤 활성화 함수를 적용합니다.
5. 출력 변환부(decoder)가 격자 전체의 예측 해 `u_pred(x,y)`를 만듭니다.

데이터 생성기의 `max_mode`는 합성 소스항에 포함할 최고 주파수를 정합니다. 모델의 `fno_modes`는 FNO 각 층에서 유지할 푸리에 성분의 수를 정합니다.

## 실습별 생성 파일

| 실습 | 주요 결과 경로 | 확인할 값 |
|---|---|---|
| 발사체 PINN | `labs/projectile/outputs/ksc_projectile/<run>/` | `validators/validator.npz`, `prediction.png`, checkpoint |
| Poisson FNO | `labs/poisson_fno/outputs/ksc_fno_<profile>/<run>/` | `final_state_test_metrics.json`, 테스트 예측 그림, checkpoint |
| 모드 수 비교 | `labs/poisson_fno/outputs/ksc_fno_ablation/<run>/` | 모드 6개·12개 설정별 metrics |

각 실행은 새 이름의 폴더에 결과를 저장합니다. 이전 실행을 이어갈 때는 노트북의 `RESUME_RUN_DIR`에 해당 결과 폴더를 지정합니다.

## 실행 설정

| 설정 | 용도 | 주요 구성 |
|---|---|---|
| `gh200` | GH200 대규모 후보 설정 | 256×256 격자, 학습/검증/테스트 2048/256/256개, 6개 층, 푸리에 모드 32개, 채널 너비 64, 2000단계 |
| `recovery` | 수업용 단축 설정 | 64×64 격자, 학습/검증/테스트 800/100/100개, 4개 층, 푸리에 모드 12개, 채널 너비 32, 400단계 |

`gh200`은 계산량을 높인 후보 설정이며, 80분 세션 안에 학습과 평가를 마치는지는 행사 전 PILOT GH200 예행연습에서 확인해야 합니다. 강사가 `gh200` 완주를 확인하지 않은 경우에는 `recovery`를 사용합니다. 두 설정은 격자·데이터·모델 크기와 학습 단계가 모두 다르므로 성능 비교용으로 사용하지 않습니다.

## 완료 체크리스트

### 발사체 PINN

- [ ] 필수 파일과 PhysicsNeMo-Sym import를 확인했습니다.
- [ ] 학습 프로세스가 종료 코드 0으로 끝났습니다.
- [ ] `validator.npz`에서 상대 L2 오차와 최대 절대 오차를 계산했습니다.
- [ ] 해석해와 PINN 예측 그래프, 학습 구간과 외삽 구간을 구분했습니다.

### Poisson FNO

- [ ] CUDA와 데이터셋 검증을 통과했습니다.
- [ ] `final_state_test_metrics.json`과 테스트 예측 그림을 확인했습니다.
- [ ] 상대 L2 오차, 전체 실행 시간, 최대 PyTorch GPU 메모리를 기록했습니다.
- [ ] 입력·정답·예측·절대 오차 그림을 해석했습니다.

## 선택 실습과 참고 자료

필수 FNO 실습을 일찍 마친 참가자는 강사 안내 후 [FNO 모드 수 비교](optional/README.md)를 진행합니다. 공식 원본의 다른 튜토리얼과 챌린지는 [OpenHackathons AI-Powered-Physics-Bootcamp](https://github.com/openhackathons-org/AI-Powered-Physics-Bootcamp)에서 확인할 수 있습니다.

[Start Here로 돌아가기](../00_Start_Here.ipynb) · [전체 과정 안내 보기](../README.md)
