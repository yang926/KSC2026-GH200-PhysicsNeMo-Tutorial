// SPDX-License-Identifier: Apache-2.0
#include <cuda_runtime.h>
#include <cerrno>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <new>

#define CUDA_OK(call) do { cudaError_t e=(call); if(e!=cudaSuccess){ \
  std::fprintf(stderr, "%s:%d %s\n", __FILE__, __LINE__, cudaGetErrorString(e)); \
  std::exit(2); }} while(0)

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
  int pageable_access = 0;
  int uses_host_page_tables = 0;
  CUDA_OK(cudaDeviceGetAttribute(
      &pageable_access, cudaDevAttrPageableMemoryAccess, 0));
  CUDA_OK(cudaDeviceGetAttribute(
      &uses_host_page_tables,
      cudaDevAttrPageableMemoryAccessUsesHostPageTables,
      0));
  if (!pageable_access) {
    std::puts(
        "SYSTEM_MEMORY result=SKIP "
        "reason=cudaDevAttrPageableMemoryAccess_is_false");
    return 0;
  }

  const char *coherency =
      uses_host_page_tables ? "ATS/hardware-coherent"
                            : "HMM/software-coherent";
  const std::size_t n = element_count(argc, argv);
  const std::size_t bytes = n * sizeof(float);
  float *x = new (std::nothrow) float[n];
  float *y = new (std::nothrow) float[n];
  if (x == nullptr || y == nullptr) {
    std::printf(
        "SYSTEM_MEMORY path=%s elements=%zu bytes=%zu result=HOST_OOM\n",
        coherency, n, bytes);
    delete[] x; delete[] y;
    return 0;
  }
  // 큰 배열에서는 첫 접촉(first touch) 비용이 크므로 CPU 코어를 모두 쓴다.
  // 초기화를 CPU에서 하므로 페이지는 Grace의 LPDDR5X에 자리 잡는다.
#pragma omp parallel for schedule(static)
  for (std::ptrdiff_t i = 0; i < static_cast<std::ptrdiff_t>(n); ++i) {
    x[i] = 1.0f;
    y[i] = 2.0f;
  }
  add_kernel<<<256,256>>>(n, x, y); CUDA_OK(cudaGetLastError());
  CUDA_OK(cudaDeviceSynchronize());
  const bool ok = std::fabs(y[0]-3.0f)<1e-6f && std::fabs(y[n-1]-3.0f)<1e-6f;
  std::printf(
      "SYSTEM_MEMORY path=%s elements=%zu bytes=%zu result=%s first=%.1f last=%.1f\n",
      coherency, n, bytes, ok?"PASS":"FAIL", y[0], y[n-1]);
  delete[] x; delete[] y;
  return ok ? 0 : 3;
}
