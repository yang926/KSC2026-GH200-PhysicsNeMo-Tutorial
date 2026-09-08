# KSC 2026 source and image provenance

이 문서는 공개 저장소와 offline image에 들어가는 자료의 출처·version·재배포 경계를 기록합니다. 법률 자문을 대신하지 않으며, 완성 image의 실제 package manifest와 license bundle을 배포 전 다시 확인해야 합니다.

## 과정 자료

| 항목 | 출처 | 적용 |
|---|---|---|
| PhysicsNeMo bootcamp adaptation | [OpenHackathons AI-Powered-Physics-Bootcamp](https://github.com/openhackathons-org/AI-Powered-Physics-Bootcamp) | 공개 upstream의 기존 고지를 보존한 KSC용 재구성 |
| `physicsnemo_sym_workflow.webp` | [NVIDIA PhysicsNeMo-Sym User Guide — PINNs Tutorials](https://docs.nvidia.com/physicsnemo/25.11/user-guide/pinns-tutorials/index.html) | PhysicsNeMo-Sym의 일반 학습 구성 절차를 설명하는 그림으로 사용 |
| `fno_data_flow.svg` | 이 저장소에서 독자 작성 | KSC FNO 실습의 입력장·푸리에 변환 블록·예측 해 흐름을 설명하는 SVG |
| KSC GH200 `01_GH200/` notebook과 `labs/gh200/` | 이 저장소에서 독자 작성 | Apache-2.0; 내부 GH200 notebook/PPT의 코드·본문·output 미복사 |
| 원본 PhysicsNeMo tutorial/challenge | [공식 OpenHackathons 저장소](https://github.com/openhackathons-org/AI-Powered-Physics-Bootcamp) | 이 저장소와 offline image에 중복 복사하지 않고 공식 링크로만 안내 |
| 내부 GH200 workshop 자료 | 공개 source에 미포함 | 파일별 서면 재배포 허가 전 복사·번역·screenshot·output 재사용 금지 |

## Offline image dependency pins

| Component | Pin | Source identity | License / notice handling |
|---|---|---|---|
| NVIDIA PhysicsNeMo | `25.11`, Linux ARM64 manifest `sha256:4e7f82e33d886828efd1e4d65236f5e44c96dfbd3d316c58723eff9b9298eda6` | [NGC PhysicsNeMo 25.11](https://catalog.ngc.nvidia.com/orgs/nvidia/physicsnemo/containers/physicsnemo/25.11) | NGC/base image terms와 image 내부 third-party notices 보존 |
| NVIDIA HPC SDK / NVPL | `25.5`, Linux ARM64 manifest `sha256:d5b8001ed137d70417454279c46f6dde335337efbbd6742a4b1c103cbf85831b` | [NGC NVHPC 25.5](https://catalog.ngc.nvidia.com/orgs/nvidia/-/containers/nvhpc/25.5-devel-cuda_multi-ubuntu24.04) | NVIDIA HPC SDK EULA와 bundled notice 확인; 외부 SIF 재배포 조건 **확인 필요** |
| Boost.ProgramOptions | `1.83.0`, 압축 파일 SHA256 `c0685b68dd44cc46574cce86c4e17c0f611b15e195be9848dfd0769a0a207628` | [Boost 1.83.0 소스 압축 파일](https://archives.boost.io/release/1.83.0/source/boost_1_83_0.tar.gz) | ProgramOptions만 정적 라이브러리로 빌드; BSL-1.0 `LICENSE_1_0.txt`를 이미지의 라이선스 묶음에 보존 |
| OpenBLAS | `v0.3.31`, archive SHA256 `6dd2a63ac9d32643b7cc636eab57bf4e57d0ed1fff926dfbc5d3d97f2d2be3a6` | [OpenMathLib/OpenBLAS](https://github.com/OpenMathLib/OpenBLAS/releases/tag/v0.3.31) | BSD-3-Clause text를 image license bundle에 보존 |
| nvbandwidth | `v0.8`, archive SHA256 `b3622945eb7fce2b4e1aea7d13de04f415f4d998db602893201a904320cf2d39` | [NVIDIA/nvbandwidth](https://github.com/NVIDIA/nvbandwidth/releases/tag/v0.8) | Apache-2.0 `LICENSE`와 bundled jsoncpp `Licenses.txt` 보존 |

`Dockerfile`과 KISTI 직접 빌드는 위 ARM64 매니페스트를 정확한 다이제스트로 고정합니다. 두 경로 모두 기반 이미지의 빌드 도구를 먼저 확인하며 운영체제의 패키지 관리자로 빌드 종속성을 설치하지 않습니다. Boost, OpenBLAS와 nvbandwidth 압축 파일의 SHA256을 검증한 뒤에만 컴파일합니다. `/etc/ksc2026-image.json`은 교육용 버전 정보이며 이미지 SBOM을 대체하지 않습니다.

## 선택 실습 후보

| 항목 | 검토 결과 | 공개 과정 결정 |
|---|---|---|
| LULESH 2.0.3 | [LLNL/LULESH](https://github.com/LLNL/LULESH) 공식 source에 BSD 조건과 DOE notice 존재 | 공식 source와 고지를 직접 pin하고 ARM64 build를 검증한 뒤 A1 활성화 가능 |
| miniSOD | 현재 검토 후보에 명시적 license가 없고 notebook이 전제한 `DIRTY_MEMORY` 구현을 확인하지 못함 | source·license·기능이 모두 확인될 때까지 A2 미포함 |
| FNO mode ablation | 기존 공개 PhysicsNeMo KSC adaptation의 선택 실습 | `02_PhysicsNeMo/optional/FNO_Mode_Ablation.ipynb`로 포함 |
| 원본 PhysicsNeMo 추가자료 | 공개 upstream에 존재 | 로컬 복사본 없이 공식 tutorial/challenge 링크로 안내; offline runtime 의존성 없음 |

## Public release gates

- [ ] ARM64 Docker image가 exact base digests로 build됨
- [ ] 기반 이미지 빌드 도구 사전 검사 로그 보존
- [ ] Boost/OpenBLAS/nvbandwidth 소스 체크섬 검증 로그 보존
- [ ] Boost BSL-1.0, OpenBLAS BSD-3-Clause, nvbandwidth Apache-2.0과 함께 제공되는 고지 확인 완료
- [ ] `/opt/ksc2026/licenses`와 base image notices readback 완료
- [ ] Docker image에서 만든 동일 artifact를 SIF로 변환함
- [ ] `apptainer exec --nv`에서 compiler, profiler, CUDA, PhysicsNeMo와 notebook smoke test 통과
- [ ] PILOT runtime network 없이 필수 동선 `00 → 01_GH200 → 02_PhysicsNeMo` 실행 가능
- [ ] `02_PhysicsNeMo/optional`의 로컬 선택 실습이 build context와 image에 포함됨
- [ ] NVIDIA software와 NGC base를 포함한 SIF의 수강생 배포 범위 확인
- [ ] private workshop material 또는 credential이 build context·history·image에 없음을 확인

## Known size trade-off

NVHPC stage의 `/opt/nvidia/hpc_sdk` 전체를 final image로 복사하면 compiler와 NVPL dependency 누락 위험은 줄지만 image가 매우 커질 수 있습니다. 구성요소를 잘라내는 최적화는 `nvc`, `-Mnvpl=blas`, CUDA compile과 runtime dependency audit를 실제 ARM64 image에서 통과한 뒤에만 수행합니다.
