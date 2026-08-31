# 선택 실습 — FNO 푸리에 모드 수 비교

필수 Poisson FNO 실습을 마친 참가자는 강사 안내 후 이 실습을 진행할 수 있습니다.

| 자료 | 비교 조건 | 기록할 결과 |
|---|---|---|
| [`FNO_Mode_Ablation.ipynb`](FNO_Mode_Ablation.ipynb) | 같은 데이터·학습 설정에서 `fno_modes=6`과 `12` 비교 | 상대 L2 오차, 파라미터 수, 전체 실행 시간, 최대 PyTorch GPU 메모리 |

## 실험 질문

1. 푸리에 모드를 늘렸을 때 테스트 오차는 얼마나 달라졌나요?
2. 파라미터 수와 최대 GPU 메모리는 얼마나 증가했나요?
3. 전체 실행 시간의 차이가 오차 감소와 균형을 이루나요?
4. 같은 난수 시드의 한 번의 실험으로 확인할 수 있는 범위는 어디까지인가요?

두 실험은 같은 축소 데이터셋과 난수 시드 `2026`을 사용합니다. 관찰 결과는 이 데이터·모델·학습 설정에 대한 값으로 기록합니다.

## 추가 학습 자료

- [OpenHackathons AI-Powered-Physics-Bootcamp](https://github.com/openhackathons-org/AI-Powered-Physics-Bootcamp)
- [원본 튜토리얼 모음](https://github.com/openhackathons-org/AI-Powered-Physics-Bootcamp/tree/main/tutorial)
- [원본 챌린지 모음](https://github.com/openhackathons-org/AI-Powered-Physics-Bootcamp/tree/main/challenge)

[PhysicsNeMo 모듈 지도로 돌아가기](../README.md) · [Start Here로 돌아가기](../../00_Start_Here.ipynb)
