# 노트북 지원 파일

이 폴더에는 번호가 붙은 실습 노트북이 호출하는 소스 코드, 설정과 강의 이미지를 모아 두었습니다.

```text
labs/
├── gh200/          # DGEMM, CUDA 메모리 예제와 도우미 함수
├── projectile/     # PhysicsNeMo-Sym 발사체 코드·설정·이미지
└── poisson_fno/    # PhysicsNeMo FNO 코드·설정·데이터 생성기·이미지
```

참가자는 [`../00_Start_Here.ipynb`](../00_Start_Here.ipynb)에서 환경을 확인한 뒤
[`01_GH200`](../01_GH200/README.md) → [`02_PhysicsNeMo`](../02_PhysicsNeMo/README.md) 순서로 진행합니다.
PhysicsNeMo의 선택 실습은 [`02_PhysicsNeMo/optional`](../02_PhysicsNeMo/optional/README.md)에만 있습니다. 지원 source를 직접 수정하는 것은 선택 실험에서 명시한 경우에만 권장합니다.

실행 파일, Nsight 보고서, 데이터셋, 체크포인트, 검증 그래프와 평가 지표는 `work/` 또는 각 실습의 `datasets/`, `outputs/` 아래에 생성됩니다. 이 결과 파일은 개인 작업공간에 저장되며 Git 배포 원본에는 포함되지 않습니다.
