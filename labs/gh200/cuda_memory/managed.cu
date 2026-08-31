// SPDX-License-Identifier: Apache-2.0
#include <cuda_runtime.h>
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

int main() {
  constexpr std::size_t n = 1u << 22;
  constexpr std::size_t bytes = n * sizeof(float);
  float *x = nullptr, *y = nullptr;
  CUDA_OK(cudaMallocManaged(&x, bytes)); CUDA_OK(cudaMallocManaged(&y, bytes));
  for (std::size_t i=0; i<n; ++i) { x[i]=1.0f; y[i]=2.0f; }
  int device = 0; CUDA_OK(cudaGetDevice(&device));
  cudaMemLocation gpu_location{};
  gpu_location.type = cudaMemLocationTypeDevice;
  gpu_location.id = device;
  CUDA_OK(cudaMemPrefetchAsync(x, bytes, gpu_location, 0, 0));
  CUDA_OK(cudaMemPrefetchAsync(y, bytes, gpu_location, 0, 0));
  add_kernel<<<256,256>>>(n, x, y); CUDA_OK(cudaGetLastError());
  CUDA_OK(cudaDeviceSynchronize());
  const bool ok = std::fabs(y[0]-3.0f)<1e-6f && std::fabs(y[n-1]-3.0f)<1e-6f;
  std::printf("managed memory result=%s first=%.1f last=%.1f\n", ok?"PASS":"FAIL", y[0], y[n-1]);
  CUDA_OK(cudaFree(x)); CUDA_OK(cudaFree(y));
  return ok ? 0 : 3;
}
