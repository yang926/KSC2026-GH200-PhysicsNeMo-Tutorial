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
  const std::size_t n = element_count(argc, argv);
  const std::size_t bytes = n * sizeof(float);
  float *x = nullptr, *y = nullptr, *dx = nullptr, *dy = nullptr;

  // 명시적 복사는 디바이스 메모리를 반드시 먼저 확보해야 합니다. HBM보다 큰
  // 요청은 여기서 실패합니다. 호스트 메모리를 잡기 전에 확인하고, 프로그램을
  // 죽이지 않고 그 사실을 결과로 보고합니다.
  const cudaError_t alloc_x = cudaMalloc(&dx, bytes);
  const cudaError_t alloc_y =
      alloc_x == cudaSuccess ? cudaMalloc(&dy, bytes) : alloc_x;
  if (alloc_x != cudaSuccess || alloc_y != cudaSuccess) {
    std::size_t free_bytes = 0, total_bytes = 0;
    cudaMemGetInfo(&free_bytes, &total_bytes);
    cudaGetLastError();
    std::printf(
        "explicit memcpy elements=%zu bytes=%zu result=OOM "
        "device_free=%zu device_total=%zu reason=%s\n",
        n, bytes, free_bytes, total_bytes,
        cudaGetErrorString(alloc_x != cudaSuccess ? alloc_x : alloc_y));
    if (dx) cudaFree(dx);
    return 0;
  }

  x = new (std::nothrow) float[n];
  y = new (std::nothrow) float[n];
  if (x == nullptr || y == nullptr) {
    std::printf(
        "explicit memcpy elements=%zu bytes=%zu result=HOST_OOM\n", n, bytes);
    delete[] x; delete[] y;
    cudaFree(dx); cudaFree(dy);
    return 0;
  }

  // 큰 배열에서는 첫 접촉(first touch) 비용이 크므로 CPU 코어를 모두 씁니다.
#pragma omp parallel for schedule(static)
  for (std::ptrdiff_t i = 0; i < static_cast<std::ptrdiff_t>(n); ++i) {
    x[i] = 1.0f;
    y[i] = 2.0f;
  }

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
