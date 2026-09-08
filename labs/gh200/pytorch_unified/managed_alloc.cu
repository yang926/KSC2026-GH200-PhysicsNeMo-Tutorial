// SPDX-License-Identifier: Apache-2.0
// KSC 2026: PyTorch가 GPU 메모리를 잡을 때 cudaMalloc 대신 cudaMallocManaged를
// 쓰도록 바꾸는 최소 할당기입니다. GH200에서는 HBM을 넘긴 텐서도 NVLink-C2C를
// 통해 Grace의 LPDDR5X에 자리 잡아 그대로 동작합니다.
//
// 빌드:
//   nvcc -O3 -shared -Xcompiler -fPIC -o managed_alloc.so managed_alloc.cu

#include <cuda_runtime.h>
#include <sys/types.h>

extern "C" {

void *ksc_managed_malloc(ssize_t size, int device, cudaStream_t stream) {
  (void)device;
  (void)stream;
  void *pointer = nullptr;
  if (cudaMallocManaged(&pointer, static_cast<size_t>(size)) != cudaSuccess) {
    cudaGetLastError();
    return nullptr;
  }
  return pointer;
}

void ksc_managed_free(void *pointer, ssize_t size, int device,
                      cudaStream_t stream) {
  (void)size;
  (void)device;
  (void)stream;
  cudaFree(pointer);
}

}  // extern "C"
