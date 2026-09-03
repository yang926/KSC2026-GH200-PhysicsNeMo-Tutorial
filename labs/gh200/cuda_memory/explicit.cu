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
  const std::size_t n = element_count(argc, argv);
  const std::size_t bytes = n * sizeof(float);
  float *x = new float[n], *y = new float[n], *dx = nullptr, *dy = nullptr;
  for (std::size_t i=0; i<n; ++i) { x[i]=1.0f; y[i]=2.0f; }
  CUDA_OK(cudaMalloc(&dx, bytes)); CUDA_OK(cudaMalloc(&dy, bytes));
  CUDA_OK(cudaMemcpy(dx, x, bytes, cudaMemcpyHostToDevice));
  CUDA_OK(cudaMemcpy(dy, y, bytes, cudaMemcpyHostToDevice));
  add_kernel<<<256,256>>>(n, dx, dy); CUDA_OK(cudaGetLastError());
  CUDA_OK(cudaMemcpy(y, dy, bytes, cudaMemcpyDeviceToHost));
  const bool ok = std::fabs(y[0]-3.0f)<1e-6f && std::fabs(y[n-1]-3.0f)<1e-6f;
  std::printf(
      "explicit memcpy elements=%zu bytes=%zu result=%s first=%.1f last=%.1f\n",
      n, bytes, ok?"PASS":"FAIL", y[0], y[n-1]);
  CUDA_OK(cudaFree(dx)); CUDA_OK(cudaFree(dy)); delete[] x; delete[] y;
  return ok ? 0 : 3;
}
