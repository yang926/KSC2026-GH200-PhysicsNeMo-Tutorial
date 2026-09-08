// SPDX-License-Identifier: Apache-2.0
#include <cuda_runtime.h>
#include <cerrno>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <cstring>

#define CUDA_OK(call) do { cudaError_t e=(call); if(e!=cudaSuccess){ \
  std::fprintf(stderr, "%s:%d %s\n", __FILE__, __LINE__, cudaGetErrorString(e)); \
  std::exit(2); }} while(0)

// 통합 메모리를 GPU에서 먼저 초기화하면 페이지가 HBM에 자리 잡고, HBM을
// 넘는 부분만 시스템 메모리로 넘어갑니다. CPU에서 초기화하면 전량이 시스템
// 메모리에 first-touch되어 Job 메모리 한도를 넘길 수 있습니다.
__global__ void init_kernel(std::size_t n, float *x, float *y) {
  for (std::size_t i = blockIdx.x * blockDim.x + threadIdx.x; i < n;
       i += blockDim.x * gridDim.x) { x[i] = 1.0f; y[i] = 2.0f; }
}

__global__ void add_kernel(std::size_t n, const float *x, float *y) {
  for (std::size_t i = blockIdx.x * blockDim.x + threadIdx.x; i < n;
       i += blockDim.x * gridDim.x) y[i] += x[i];
}

// 상한은 HBM보다 큰 배열을 만들 수 있도록 열어 둔다. 실제로 안전한 크기는
// 노트북이 실행 시점의 HBM 용량과 시스템 가용 메모리에서 계산해 전달한다.
static std::size_t element_count(int argc, char **argv) {
  constexpr std::size_t fallback = 1u << 24;
  constexpr unsigned long long limit = 1ull << 36;  // 배열 하나 256 GiB
  if (argc < 2) return fallback;
  errno = 0;
  char *end = nullptr;
  const unsigned long long value = std::strtoull(argv[1], &end, 10);
  if (errno || end == argv[1] || *end != '\0' || value < 1024 ||
      value > limit) {
    std::fprintf(stderr, "elements must be an integer from 1024 to %llu\n",
                 limit);
    std::exit(2);
  }
  return static_cast<std::size_t>(value);
}

int main(int argc, char **argv) {
  const std::size_t n = element_count(argc, argv);
  const char *mode = argc > 2 ? argv[2] : "prefetch";
  if (std::strcmp(mode, "prefetch") != 0 && std::strcmp(mode, "demand") != 0) {
    std::fprintf(stderr, "mode must be prefetch or demand\n");
    return 2;
  }
  const bool use_prefetch = std::strcmp(mode, "prefetch") == 0;

  // 세 번째 인수로 초기화 위치를 고릅니다. 기본은 cpu입니다.
  const char *init_where = argc > 3 ? argv[3] : "cpu";
  if (std::strcmp(init_where, "cpu") != 0 && std::strcmp(init_where, "gpu") != 0) {
    std::fprintf(stderr, "init must be cpu or gpu\n");
    return 2;
  }
  const bool init_on_gpu = std::strcmp(init_where, "gpu") == 0;
  const std::size_t bytes = n * sizeof(float);
  float *x = nullptr, *y = nullptr;
  // 통합 메모리는 HBM을 넘겨도 할당됩니다. 시스템 메모리까지 부족할 때만
  // 실패하며, 그 경우에도 죽지 않고 결과로 보고합니다.
  const cudaError_t alloc_x = cudaMallocManaged(&x, bytes);
  const cudaError_t alloc_y =
      alloc_x == cudaSuccess ? cudaMallocManaged(&y, bytes) : alloc_x;
  if (alloc_x != cudaSuccess || alloc_y != cudaSuccess) {
    std::size_t free_bytes = 0, total_bytes = 0;
    cudaMemGetInfo(&free_bytes, &total_bytes);
    cudaGetLastError();
    std::printf(
        "managed memory mode=%s elements=%zu bytes=%zu result=OOM "
        "device_free=%zu device_total=%zu reason=%s\n",
        mode, n, bytes, free_bytes, total_bytes,
        cudaGetErrorString(alloc_x != cudaSuccess ? alloc_x : alloc_y));
    if (x) cudaFree(x);
    return 0;
  }
  if (init_on_gpu) {
    init_kernel<<<1024, 256>>>(n, x, y);
    CUDA_OK(cudaGetLastError());
    CUDA_OK(cudaDeviceSynchronize());
  } else {
    // 큰 배열에서는 첫 접촉(first touch) 비용이 크므로 CPU 코어를 모두 씁니다.
#pragma omp parallel for schedule(static)
    for (std::ptrdiff_t i = 0; i < static_cast<std::ptrdiff_t>(n); ++i) {
      x[i] = 1.0f;
      y[i] = 2.0f;
    }
  }
  if (use_prefetch) {
    // HBM보다 큰 배열에서는 전량 사전 이동이 불가능하므로 런타임이 요청을
    // 부분적으로만 반영하거나 무시할 수 있습니다.
    int device = 0; CUDA_OK(cudaGetDevice(&device));
    cudaMemLocation gpu_location{};
    gpu_location.type = cudaMemLocationTypeDevice;
    gpu_location.id = device;
    CUDA_OK(cudaMemPrefetchAsync(x, bytes, gpu_location, 0, 0));
    CUDA_OK(cudaMemPrefetchAsync(y, bytes, gpu_location, 0, 0));
  }
  add_kernel<<<256,256>>>(n, x, y); CUDA_OK(cudaGetLastError());
  CUDA_OK(cudaDeviceSynchronize());
  const bool ok = std::fabs(y[0]-3.0f)<1e-6f && std::fabs(y[n-1]-3.0f)<1e-6f;
  std::printf(
      "managed memory mode=%s init=%s elements=%zu bytes=%zu result=%s "
      "first=%.1f last=%.1f\n",
      mode, init_where, n, bytes, ok?"PASS":"FAIL", y[0], y[n-1]);
  CUDA_OK(cudaFree(x)); CUDA_OK(cudaFree(y));
  return ok ? 0 : 3;
}
