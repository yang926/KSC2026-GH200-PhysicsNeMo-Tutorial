// SPDX-License-Identifier: Apache-2.0
// KSC 2026: the same BLAS call is linked once with OpenBLAS and once with NVPL.
#define _POSIX_C_SOURCE 200809L
#include <errno.h>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <time.h>

extern void dgemm_(const char *transa, const char *transb, const int *m,
                   const int *n, const int *k, const double *alpha,
                   const double *a, const int *lda, const double *b,
                   const int *ldb, const double *beta, double *c,
                   const int *ldc);

static double now_seconds(void) {
  struct timespec value;
  clock_gettime(CLOCK_MONOTONIC, &value);
  return (double)value.tv_sec + 1.0e-9 * (double)value.tv_nsec;
}

static int positive_int(const char *text, int fallback) {
  if (text == NULL) return fallback;
  errno = 0;
  char *end = NULL;
  long value = strtol(text, &end, 10);
  if (errno || end == text || *end != '\0' || value < 1 || value > 32768)
    return fallback;
  return (int)value;
}

int main(int argc, char **argv) {
  const int n = positive_int(argc > 1 ? argv[1] : NULL, 1024);
  const int repeats = positive_int(argc > 2 ? argv[2] : NULL, 3);
  const size_t elements = (size_t)n * (size_t)n;
  double *a = NULL, *b = NULL, *c = NULL;
  if (posix_memalign((void **)&a, 64, elements * sizeof(double)) ||
      posix_memalign((void **)&b, 64, elements * sizeof(double)) ||
      posix_memalign((void **)&c, 64, elements * sizeof(double))) {
    fprintf(stderr, "allocation failed for n=%d\n", n);
    free(a); free(b); free(c);
    return 2;
  }

  for (size_t i = 0; i < elements; ++i) {
    a[i] = 1.0 / (double)(1 + (i % 97));
    b[i] = 1.0 / (double)(1 + (i % 89));
    c[i] = 0.0;
  }

  const char trans = 'N';
  const double alpha = 1.0, beta = 0.0;
  double best = HUGE_VAL;
  for (int repeat = 0; repeat < repeats; ++repeat) {
    const double start = now_seconds();
    dgemm_(&trans, &trans, &n, &n, &n, &alpha, a, &n, b, &n, &beta,
           c, &n);
    const double elapsed = now_seconds() - start;
    if (elapsed < best) best = elapsed;
  }

  double checksum = 0.0;
  for (size_t i = 0; i < elements; i += elements / 64 + 1) checksum += c[i];
  const double gflops = (2.0 * (double)n * (double)n * (double)n) / best / 1.0e9;
  printf("n=%d repeats=%d best_seconds=%.6f gflops=%.2f checksum=%.9e\n",
         n, repeats, best, gflops, checksum);

  free(a); free(b); free(c);
  return 0;
}
