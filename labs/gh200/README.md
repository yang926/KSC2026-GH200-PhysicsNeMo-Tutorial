# GH200 실습 지원 파일

이 폴더에는 [Grace CPU 컴파일·튜닝](../../01_GH200/01_CPU_Compile_and_Tune.ipynb)과 [Hopper GPU 메모리·프로파일링](../../01_GH200/02_GPU_Memory_Profile.ipynb) 노트북이 호출하는 소스 코드와 도우미 함수가 있습니다.

| 경로 | 역할 | 생성 결과 |
|---|---|---|
| `notebook_utils.py` | 명령 실행, 도구 확인, 이미지 구성 정보 읽기 | 노트북 출력 |
| `blas/dgemm.c` | 같은 DGEMM 호출로 행렬 곱셈 수행 | 체크섬, 실행 시간, GFLOP/s |
| `blas/Makefile` | OpenBLAS·NVPL 빌드 구성 정의 | `work/gh200/bin/dgemm-*` |
| `cuda_memory/explicit.cu` | 명시적 호스트↔디바이스 할당·복사 | `cuda-explicit` |
| `cuda_memory/managed.cu` | `cudaMallocManaged`와 사전 이동 | `cuda-managed` |
| `cuda_memory/hmm.cu` | 시스템 할당 메모리의 GPU 직접 접근 여부와 ATS·HMM 경로 확인 | `cuda-system` 또는 `SKIP` |

컴파일러, 수학 라이브러리, 프로파일러와 nvbandwidth는 SIF에 설치되어 있습니다. 노트북의 지시에 따라 이 소스를 빌드하며 계산 노드에서 패키지 설치나 소스 다운로드를 수행하지 않습니다.

이 예제는 KSC 2026 실습용으로 작성했으며 각 소스 파일에 Apache-2.0 SPDX 식별자를 기록합니다.

[01_GH200 모듈 지도로 돌아가기](../../01_GH200/README.md)
