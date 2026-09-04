# 행사 후 — 개인 환경에서 PhysicsNeMo 사용하기

이 문서는 **KSC 2026이 끝난 뒤** 읽는 내용입니다. 행사 당일 계산 노드는 인터넷을 쓰지 않으므로 아래 명령은 실행하지 않습니다.

목적에 따라 두 갈래로 나뉩니다.

---

## 갈래 1 — 이 실습 코드를 같은 API로 그대로 재현하고 싶다

이 과정의 코드는 PhysicsNeMo **25.11**의 `Solver` / `Domain` / `Constraint` API를 씁니다. 그대로 돌리려면 같은 컨테이너가 필요합니다.

- **Linux/ARM64 + Apptainer**: 행사 SIF와 같은 이미지 계약을 사용합니다.
- **GPU Linux + Docker + NVIDIA Container Toolkit**: `nvcr.io/nvidia/physicsnemo/physicsnemo:25.11` NGC 컨테이너에 실습 파일을 마운트합니다.

호스트 아키텍처, NVIDIA 드라이버, 컨테이너 런타임이 모두 맞아야 합니다. 행사 SIF가 모든 개인 PC에서 그대로 실행된다고 가정하지 마세요.

---

## 갈래 2 — 새 프로젝트를 최신 API로 시작하고 싶다

PhysicsNeMo v2.0부터 Sym 기능이 본체 저장소에 통합되었습니다. 아래는 **기본·CPU 검증용** 명령입니다.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip

# 기본 기능만 필요한 경우
python -m pip install nvidia-physicsnemo

# 물리식 잔차와 Sym 기능까지 필요한 경우
python -m pip install "nvidia-physicsnemo[sym]"
```

**GPU 환경에서는 위 명령을 그대로 복사하지 마세요.** [공식 설치 안내](https://docs.nvidia.com/physicsnemo/latest/getting-started/installation.html)의 호환표에서 자신의 CUDA·PyTorch 조합을 먼저 확인하고, `cu12` 또는 `cu13` extra를 `sym`과 함께 선택하거나 호환되는 PyTorch를 먼저 설치합니다. 운영체제·드라이버·CUDA 버전에 관계없이 통하는 단일 GPU 설치 명령은 없습니다.

설치 배포 이름은 `nvidia-physicsnemo`, Python import 이름은 `physicsnemo`입니다. 배포 이름에는 하이픈이 들어가지만 `import nvidia-physicsnemo`라고 쓰지 않습니다.

설치 확인:

```python
from importlib.metadata import version
import torch
import physicsnemo
import physicsnemo.sym          # sym extra를 설치한 경우

print("PhysicsNeMo:", version("nvidia-physicsnemo"))
print("CUDA 사용 가능:", torch.cuda.is_available())
```

`torch.cuda.is_available()`이 `False`이면 PhysicsNeMo import 성공과는 별개로 NVIDIA 드라이버·CUDA가 연결된 실행 환경인지 확인해야 합니다.

> **API 호환성 주의**
> 이 과정의 25.11 코드는 v2.0 환경에 그대로 복사해 실행하는 예제가 아닙니다. v2.0에서는 `Solver` / `Domain` / `Constraint` 중심 구성 대신 더 명시적인 PyTorch 학습 루프와 새 Sym API를 씁니다. 새 프로젝트는 [v2.0 migration guide](https://github.com/NVIDIA/physicsnemo/blob/main/v2.0-MIGRATION-GUIDE.md)와 최신 예제를 기준으로 작성하세요. 64-bit ARM CUDA 환경은 최신 공식 문서의 `uv` 설치 지침을 우선 확인합니다.

---

## 참고 자료

- [PhysicsNeMo 25.11 문서](https://docs.nvidia.com/physicsnemo/25.11/) — 이 과정의 기준 문서
- [최신 PhysicsNeMo 문서](https://docs.nvidia.com/physicsnemo/latest/)
- [최신 설치 안내](https://docs.nvidia.com/physicsnemo/latest/getting-started/installation.html)
- [v2.0 Migration Guide](https://github.com/NVIDIA/physicsnemo/blob/main/v2.0-MIGRATION-GUIDE.md)
- [PhysicsNeMo NGC 컨테이너](https://catalog.ngc.nvidia.com/orgs/nvidia/physicsnemo/containers/physicsnemo)
- [PhysicsNeMo GitHub](https://github.com/NVIDIA/physicsnemo)
- [FNO 논문](https://arxiv.org/abs/2010.08895) · [PINN 논문](https://www.sciencedirect.com/science/article/pii/S0021999118307125)
- [OpenHackathons AI-Powered-Physics-Bootcamp 원본 과정](https://github.com/openhackathons-org/AI-Powered-Physics-Bootcamp)

[전체 과정 안내로 돌아가기](README.md)
