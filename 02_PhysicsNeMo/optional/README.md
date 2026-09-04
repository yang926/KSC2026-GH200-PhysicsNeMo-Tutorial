# 선택 실습 — FNO 푸리에 모드 수 비교

필수 Poisson FNO 실습을 마친 참가자는 강사 안내 후 이 실습을 진행할 수 있습니다. 같은 조건에서 `fno_modes`만 바꾼 두 실행의 정확도와 계산 비용을 측정하고 실제 비율을 자동으로 비교합니다.

| 자료 | 비교 조건 | 자동 비교 결과 |
|---|---|---|
| [`FNO_Mode_Ablation.ipynb`](FNO_Mode_Ablation.ipynb) | 같은 데이터·학습 설정에서 `fno_modes=6`과 `12` 비교 | 학습 전후 상대 L2, 파라미터 수, 전체 실행 시간, 최대 PyTorch GPU 메모리, 모드 12/6 비율 |

## 강사와 함께 확인할 해석 지점

- 푸리에 모드를 늘렸을 때의 테스트 오차, 파라미터 수, 최대 GPU 메모리, 전체 실행 시간 변화를 함께 봅니다.
- 12/6 비율은 추가 계산 비용과 오차 변화의 크기를 같은 화면에서 비교합니다.
- 같은 난수 시드의 한 번의 실험은 현재 데이터·모델·학습 설정에 대한 관찰이며 일반적인 우위를 입증하지 않습니다.

두 실험은 같은 축소 데이터셋과 난수 시드 `2026`을 사용합니다. 모델의 모드 수와 결과 폴더 이름만 다르다는 검사를 통과한 뒤 실행합니다.

## 추가 학습 자료

- [OpenHackathons AI-Powered-Physics-Bootcamp](https://github.com/openhackathons-org/AI-Powered-Physics-Bootcamp)
- [원본 튜토리얼 모음](https://github.com/openhackathons-org/AI-Powered-Physics-Bootcamp/tree/main/tutorial)
- [원본 챌린지 모음](https://github.com/openhackathons-org/AI-Powered-Physics-Bootcamp/tree/main/challenge)

[PhysicsNeMo 모듈 지도로 돌아가기](../README.md) · [Start Here로 돌아가기](../../00_Start_Here.ipynb)
