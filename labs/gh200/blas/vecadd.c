// SPDX-License-Identifier: Apache-2.0
// KSC 2026: 참가자가 직접 컴파일 명령을 입력해 보는 최소 예제.
//
// 같은 소스를 -mcpu=native 있이 / 없이 두 번 빌드해 비교하는 것이 목적입니다.
// DGEMM은 미리 빌드된 BLAS를 호출하므로 컴파일 옵션의 효과가 드러나지 않지만,
// 이 파일은 계산 루프가 소스 안에 있어 컴파일러가 실제로 코드를 생성합니다.
#define _POSIX_C_SOURCE 200809L
#include <stdio.h>
#include <stdlib.h>
#include <time.h>

static double now_seconds(void) {
  struct timespec value;
  clock_gettime(CLOCK_MONOTONIC, &value);
  return (double)value.tv_sec + 1.0e-9 * (double)value.tv_nsec;
}

int main(int argc, char **argv) {
  // 기본 6천4백만 원소. 배열 3개 x 8바이트 = 약 1.5 GiB.
  const long n = (argc > 1) ? strtol(argv[1], NULL, 10) : 64L * 1024L * 1024L;
  const int repeats = (argc > 2) ? atoi(argv[2]) : 5;
  if (n < 1024L || n > (1L << 32) || repeats < 1 || repeats > 50) {
    fprintf(stderr, "usage: vecadd [elements 1024..2^32] [repeats 1..50]\n");
    return 2;
  }

  double *a = malloc((size_t)n * sizeof(double));
  double *b = malloc((size_t)n * sizeof(double));
  double *c = malloc((size_t)n * sizeof(double));
  if (!a || !b || !c) {
    fprintf(stderr, "result=HOST_OOM elements=%ld\n", n);
    free(a); free(b); free(c);
    return 1;
  }

  // 첫 접촉을 계산과 같은 스레드 배치로 맞춥니다.
#pragma omp parallel for schedule(static)
  for (long i = 0; i < n; ++i) {
    a[i] = 1.0;
    b[i] = 2.0;
    c[i] = 0.0;
  }

  double best = 1.0e30;
  for (int repeat = 0; repeat < repeats; ++repeat) {
    const double started = now_seconds();
#pragma omp parallel for schedule(static)
    for (long i = 0; i < n; ++i) {
      c[i] = a[i] + 2.5 * b[i];
    }
    const double elapsed = now_seconds() - started;
    if (elapsed < best) best = elapsed;
  }

  // 최적화로 루프가 통째로 사라지지 않도록 결과를 사용합니다.
  double checksum = 0.0;
  for (long i = 0; i < n; i += n / 64 + 1) checksum += c[i];

  // 배열 3개를 오가므로 3 x 8바이트/원소.
  const double gib_per_s = (3.0 * (double)n * 8.0) / best / (1024.0 * 1024.0 * 1024.0);
  printf("n=%ld repeats=%d best_seconds=%.6f mem_GiB_per_s=%.2f checksum=%.9e\n",
         n, repeats, best, gib_per_s, checksum);

  free(a); free(b); free(c);
  return 0;
}
