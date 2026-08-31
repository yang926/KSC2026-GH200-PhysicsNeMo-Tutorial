# SPDX-License-Identifier: Apache-2.0
BUILD_DIR ?= ../../../work/gh200/bin
OPENBLAS_PREFIX ?= /opt/ksc2026/vendor/openblas
MATRIX_SIZE ?= 1024
REPEATS ?= 3
THREADS ?= 16

.PHONY: all openblas nvpl run clean

all: openblas nvpl

$(BUILD_DIR):
	mkdir -p "$@"

openblas: $(BUILD_DIR)
	gcc -O3 -mcpu=native -fopenmp dgemm.c -o "$(BUILD_DIR)/dgemm-openblas" \
		-L"$(OPENBLAS_PREFIX)/lib" -Wl,-rpath,"$(OPENBLAS_PREFIX)/lib" -lopenblas

nvpl: $(BUILD_DIR)
	nvc -O3 -fast -mp dgemm.c -o "$(BUILD_DIR)/dgemm-nvpl" -Mnvpl=blas

run:
	OMP_NUM_THREADS="$(THREADS)" OPENBLAS_NUM_THREADS="$(THREADS)" \
		"$(BUILD_DIR)/dgemm-openblas" "$(MATRIX_SIZE)" "$(REPEATS)"
	OMP_NUM_THREADS="$(THREADS)" "$(BUILD_DIR)/dgemm-nvpl" \
		"$(MATRIX_SIZE)" "$(REPEATS)"

clean:
	rm -f "$(BUILD_DIR)/dgemm-openblas" "$(BUILD_DIR)/dgemm-nvpl"
