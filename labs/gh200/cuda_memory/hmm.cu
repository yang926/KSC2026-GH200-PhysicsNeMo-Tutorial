// SPDX-License-Identifier: Apache-2.0
#include <cuda_runtime.h>
#include <cerrno>
#include <cmath>
#include <cstdio>
#include <cstdlib>

#define CUDA_OK(call) do { cudaError_t e=(call); if(e!=cudaSuccess){ \
  std::fprintf(stderr, "%s:%d %s\n", __FILE__, __LINE__, cudaGetErrorString(e)); \
  std::exit(2); }} while(0)

__global__ void add_kernel(std::size_t n, const float *x, float *y) {
  for (std::size_t i = blockIdx.x * blockDim.x + threadIdx.x; i < n;
       i += blockDim.x * gridDim.x) y[i] += x[i];
}

static std::size_t element_count(int argc, char **argv) {
  constexpr std::size_t fallback = 1u << 24;
  if (argc < 2) return fallback;
  errno = 0;
  char *end = nullptr;
  const unsigned long long value = std::strtoull(argv[1], &end, 10);
  if (errno || end == argv[1] || *end != '\0' || value < 1024 ||
      value > (1ull << 28)) {
    std::fprintf(stderr, "elements must be an integer from 1024 to %llu\n",
                 1ull << 28);
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
  float *x = new float[n], *y = new float[n];
  for (std::size_t i=0; i<n; ++i) { x[i]=1.0f; y[i]=2.0f; }
  add_kernel<<<256,256>>>(n, x, y); CUDA_OK(cudaGetLastError());
  CUDA_OK(cudaDeviceSynchronize());
  const bool ok = std::fabs(y[0]-3.0f)<1e-6f && std::fabs(y[n-1]-3.0f)<1e-6f;
  std::printf(
      "SYSTEM_MEMORY path=%s elements=%zu bytes=%zu result=%s first=%.1f last=%.1f\n",
      coherency, n, bytes, ok?"PASS":"FAIL", y[0], y[n-1]);
  delete[] x; delete[] y;
  return ok ? 0 : 3;
}
