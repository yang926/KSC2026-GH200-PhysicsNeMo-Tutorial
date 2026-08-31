#!/usr/bin/env bash
# Static contracts for the single shared, role-free KSC 2026 launcher.

set -Eeuo pipefail
set -f
umask 077
export LC_ALL=C

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
admin_dir="$(cd -- "$script_dir/.." && pwd -P)"
installer="$admin_dir/install-participants.sh"
publisher="$admin_dir/../publish-course.sh"
runtime_dir="$(cd -- "$admin_dir/../../participant" && pwd -P)"
runtime_lock_test="$script_dir/test-runtime-lock.py"

bash -n "$installer" "$publisher" "$runtime_dir/ksc2026" \
    "$runtime_dir/start-jupyter" "$runtime_dir/jupyter-job.sh"
[[ -x "$runtime_lock_test" ]] || {
    printf 'Runtime lock test is not executable: %s\n' "$runtime_lock_test" >&2
    exit 1
}

# A central deployment is the only installation step. It must never carry a
# participant roster, role route, fixed compute node, or a static tunnel.
for path in "$installer" "$publisher" "$runtime_dir/ksc2026" \
    "$runtime_dir/start-jupyter" "$runtime_dir/session-controller.py" \
    "$runtime_dir/jupyter-job.sh"; do
    if rg -n -- 'account[-_]map|instructor-route|KSC_STUDENT|KSC_INSTRUCTOR|--nodelist|--exclude|--exclusive' "$path"; then
        printf 'Unified runtime still contains a role, roster, or fixed-node contract: %s\n' "$path" >&2
        exit 1
    fi
done

for marker in \
    'Default: dry-run' \
    'APPLY_REQUIRES_CENTRAL_OWNER' \
    'KSC_LOGIN_HOST' \
    'SITE_ENV_LOGIN_HOST_INVALID' \
    'CENTRAL_ENTRYPOINT_IMMUTABLE_CONTENT_MISMATCH' \
    '/scratch/hackathon/ksc2026/bin/ksc2026'; do
    grep -Fq -- "$marker" "$installer" || {
        printf 'Installer marker missing: %s\n' "$marker" >&2
        exit 1
    }
done

for marker in \
    'KSC_LOGIN_HOST' \
    'allowed_site_keys=' \
    'deployment_lock="${admin_root}/deployment.lock"' \
    'flock -x -n 9'; do
    grep -Fq -- "$marker" "$publisher" || {
        printf 'Publisher marker missing: %s\n' "$marker" >&2
        exit 1
    }
done

for marker in \
    'exec 9<"$deployment_lock"' \
    'flock -s 9' \
    'stat -Lc '\''%d:%i'\'' /dev/fd/9' \
    'without close-on-exec'; do
    grep -Fq -- "$marker" "$runtime_dir/ksc2026" || {
        printf 'Shared wrapper lock marker missing: %s\n' "$marker" >&2
        exit 1
    }
done

if grep -Fq 'source "$site_env"' "$publisher"; then
    printf 'Publisher must parse site.env as data, not execute it.\n' >&2
    exit 1
fi

help_output="$(bash "$installer" --help)"
for expected in \
    'Default: dry-run' \
    '--apply' \
    '/scratch/hackathon/ksc2026/bin/ksc2026' \
    'never writes inside /scratch/<user>' \
    'runs --apply without sudo'; do
    [[ "$help_output" == *"$expected"* ]] || {
        printf 'Installer help is missing required text: %s\n' "$expected" >&2
        exit 1
    }
done

temporary_output="$(mktemp "${TMPDIR:-/tmp}/ksc2026-unified-admin.XXXXXXXX")"
trap 'rm -f -- "$temporary_output"' EXIT
if bash "$installer" --account-map /tmp/does-not-exist >"$temporary_output" 2>&1; then
    printf 'Installer unexpectedly accepted the removed account-map option.\n' >&2
    exit 1
fi
grep -Fq 'Unknown option: --account-map' "$temporary_output"

if bash "$installer" >"$temporary_output" 2>&1; then
    printf 'Installer unexpectedly accepted missing protected site configuration.\n' >&2
    exit 1
fi
grep -Fq 'KSC_INSTALL_ERROR=SITE_ENV_REQUIRED' "$temporary_output"

# Parse the public example with the actual controller parser. It is a data
# contract; placeholder rejection belongs to deployment, not this parser test.
before_cache="$(find "$runtime_dir" -type d -name __pycache__ -print | sort)"
python3 -B - "$runtime_dir" <<'PY'
import importlib.util
import pathlib
import sys

runtime_dir = pathlib.Path(sys.argv[1])
spec = importlib.util.spec_from_file_location("ksc2026_unified_controller_test", runtime_dir / "session-controller.py")
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)
values = module.parse_site_config(runtime_dir / "site.env.example")
assert values["KSC_LOGIN_HOST"] == "REPLACE_WITH_EVENT_LOGIN_HOST"
assert values["KSC_CPUS_PER_TASK"] == ""
assert values["KSC_MEMORY"] == ""
PY
after_cache="$(find "$runtime_dir" -type d -name __pycache__ -print | sort)"
[[ "$before_cache" == "$after_cache" ]] || {
    printf 'Static site configuration parsing created Python cache files.\n' >&2
    exit 1
}

"$runtime_lock_test"
printf 'UNIFIED_ADMIN_INSTALLER_TESTS=PASS\n'
