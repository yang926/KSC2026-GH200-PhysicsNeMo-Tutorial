#!/usr/bin/env bash
# Installer for one central KSC 2026 platform and one shared command.
# Default execution is a read-only dry-run.

set -Eeuo pipefail
set -f
umask 077
export LC_ALL=C

usage() {
    cat <<'EOF'
Usage:
  install-participants.sh \
    --site-env /secure/operator/site.env \
    --central-owner <CENTRAL_OWNER_ACCOUNT> \
    [--apply]

Default: dry-run. Add --apply only after every planned action is reviewed.
If /scratch/hackathon/ksc2026 is absent, the selected central owner creates it
as mode 0755 and then runs --apply without sudo. If that fixed child path is a
symlink or another file type, or is owned by a different account, stop and ask
a KISTI administrator to resolve the exact path; do not repair it in place.
Root and other accounts cannot apply a deployment.

The shared command is installed once at:
  /scratch/hackathon/ksc2026/bin/ksc2026

Each authenticated user creates private session and workspace directories on
first use. This installer never writes inside /scratch/<user>.

The already-staged SIF and course release are not copied. Their exact paths and
the SIF SHA-256 come from site.env and are verified before central changes.
No password, OTP, key, token, login host, IP, node, port, or account list is
embedded in the shared command.
EOF
}

die() {
    printf 'KSC_INSTALL_ERROR=%s\n' "$1" >&2
    exit 1
}

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
repo_root="$(cd -- "$script_dir/../../.." && pwd -P)"
source_dir="$repo_root/operations/participant"
site_env=
central_owner=
central_parent=/scratch/hackathon
central_root=/scratch/hackathon/ksc2026
trusted_system_apptainer=/apps/common/apptainer/1.4.5/aarch64/bin/apptainer
apply=0

while (( $# > 0 )); do
    case "$1" in
        --site-env) (( $# >= 2 )) || die MISSING_SITE_ENV_VALUE; site_env=$2; shift 2 ;;
        --central-owner) (( $# >= 2 )) || die MISSING_CENTRAL_OWNER_VALUE; central_owner=$2; shift 2 ;;
        --apply) apply=1; shift ;;
        -h|--help) usage; exit 0 ;;
        *) printf 'Unknown option: %s\n' "$1" >&2; usage >&2; exit 2 ;;
    esac
done

[[ -n "$site_env" ]] || die SITE_ENV_REQUIRED
[[ -n "$central_owner" ]] || die CENTRAL_OWNER_REQUIRED
[[ "$site_env" == /* ]] || die INPUT_PATH_MUST_BE_ABSOLUTE
[[ "$central_owner" =~ ^[A-Za-z_][A-Za-z0-9._-]*$ ]] || die CENTRAL_OWNER_INVALID

for command_name in awk bash cat chmod cmp dirname flock grep head id install mktemp mv python3 readlink rm sha256sum stat; do
    command -v "$command_name" >/dev/null 2>&1 || die "MISSING_COMMAND_${command_name}"
done
stat -c '%u:%a' / >/dev/null 2>&1 || die GNU_STAT_REQUIRED
readlink -f / >/dev/null 2>&1 || die GNU_READLINK_REQUIRED

central_uid="$(id -u "$central_owner" 2>/dev/null)" || die CENTRAL_OWNER_NOT_FOUND
[[ "$central_uid" =~ ^[0-9]+$ ]] || die CENTRAL_OWNER_UID_INVALID
actor_uid="$(id -u)"
if (( apply == 1 )) && [[ "$actor_uid" != "$central_uid" ]]; then
    die APPLY_REQUIRES_CENTRAL_OWNER
fi
[[ -d "$central_parent" && ! -L "$central_parent" ]] || die CENTRAL_PARENT_NOT_SAFE
[[ "$(readlink -f "$central_parent")" == "$central_parent" ]] || die CENTRAL_PARENT_MUST_BE_CANONICAL
[[ "$(stat -c '%u:%a' "$central_parent")" == "0:1777" ]] || die CENTRAL_PARENT_OWNER_OR_MODE_MISMATCH
[[ -d "$central_root" && ! -L "$central_root" ]] || die CENTRAL_ROOT_MUST_BE_CREATED_BY_OWNER
[[ "$(readlink -f "$central_root")" == "$central_root" ]] || die CENTRAL_ROOT_MUST_BE_CANONICAL
[[ "$(stat -c '%u' "$central_root")" == "$central_uid" ]] || die CENTRAL_ROOT_OWNER_MISMATCH

mode_value() { stat -c '%a' "$1"; }
not_group_world_writable() {
    local mode
    mode="$(mode_value "$1")" || return 1
    [[ "$mode" =~ ^[0-7]{3,4}$ ]] && (( (8#$mode & 8#022) == 0 ))
}
user_can_traverse() {
    local mode
    mode="$(mode_value "$1")" || return 1
    [[ "$mode" =~ ^[0-7]{3,4}$ ]] && (( (8#$mode & 8#005) == 8#005 ))
}
not_group_world_writable "$central_root" || die CENTRAL_ROOT_WRITABLE_BY_USER
user_can_traverse "$central_root" || die CENTRAL_ROOT_NOT_USER_TRAVERSABLE
if (( apply == 1 )) && [[ ! -w "$central_root" ]]; then
    die CENTRAL_ROOT_NOT_WRITABLE_BY_OWNER
fi

admin_root="$central_root/admin"
deployment_lock="$admin_root/deployment.lock"
[[ -d "$admin_root" && ! -L "$admin_root" &&
   "$(readlink -f "$admin_root")" == "$admin_root" &&
   "$(stat -c '%u:%a' "$admin_root")" == "$central_uid:755" ]] ||
    die CENTRAL_ADMIN_DIRECTORY_NOT_SAFE
[[ -f "$deployment_lock" && ! -L "$deployment_lock" &&
   "$(stat -c '%u:%a:%h' "$deployment_lock")" == "$central_uid:644:1" ]] ||
    die CENTRAL_DEPLOYMENT_LOCK_NOT_SAFE
exec 9<>"$deployment_lock"
flock -x -n 9 || die CENTRAL_DEPLOYMENT_LOCK_BUSY

[[ -f "$site_env" && ! -L "$site_env" && -r "$site_env" ]] || die SITE_ENV_NOT_SAFE
[[ "$(stat -c '%u' "$site_env")" == "$central_uid" ]] || die SITE_ENV_OWNER_MISMATCH
not_group_world_writable "$site_env" || die SITE_ENV_WRITABLE_BY_USER
grep -Eq '(^|=)REPLACE_|<[^>]+>' "$site_env" && die SITE_ENV_HAS_PLACEHOLDER

declare -A site=()
line_number=0
while IFS= read -r raw || [[ -n "$raw" ]]; do
    (( line_number += 1 ))
    [[ "$raw" != *$'\r'* ]] || die "SITE_ENV_CRLF_LINE_${line_number}"
    line="${raw#"${raw%%[![:space:]]*}"}"
    line="${line%"${line##*[![:space:]]}"}"
    [[ -n "$line" && "${line:0:1}" != '#' ]] || continue
    [[ "$line" == *=* ]] || die "SITE_ENV_BAD_LINE_${line_number}"
    key="${line%%=*}"; value="${line#*=}"
    [[ "$key" =~ ^KSC_[A-Z0-9_]+$ ]] || die "SITE_ENV_BAD_KEY_LINE_${line_number}"
    if [[ -z "$value" && "$key" != KSC_CPUS_PER_TASK && "$key" != KSC_MEMORY ]]; then
        die "SITE_ENV_EMPTY_VALUE_LINE_${line_number}"
    fi
    [[ -z "${site[$key]+x}" ]] || die "SITE_ENV_DUPLICATE_${key}"
    site[$key]=$value
done <"$site_env"

for key in KSC_SHARED_ROOT KSC_LOGIN_HOST KSC_APPTAINER KSC_IMAGE KSC_IMAGE_SHA256 KSC_COURSE_RELEASE KSC_JOB_SCRIPT; do
    [[ -n "${site[$key]:-}" ]] || die "SITE_ENV_MISSING_${key}"
done
[[ "${site[KSC_SHARED_ROOT]}" == "$central_root" ]] || die SITE_ENV_SHARED_ROOT_MISMATCH
[[ "${site[KSC_LOGIN_HOST]}" =~ ^[A-Za-z0-9]([A-Za-z0-9.-]*[A-Za-z0-9])?$ ]] || die SITE_ENV_LOGIN_HOST_INVALID
[[ "${site[KSC_JOB_SCRIPT]}" == "$central_root/slurm/jupyter-job.sh" ]] || die SITE_ENV_JOB_SCRIPT_MISMATCH
[[ "${site[KSC_APPTAINER]}" == /* ]] || die SITE_ENV_APPTAINER_MUST_BE_ABSOLUTE
[[ "${site[KSC_APPTAINER]}" == "$trusted_system_apptainer" ]] || die SITE_ENV_APPTAINER_NOT_APPROVED
[[ "${site[KSC_IMAGE]}" == "$central_root"/* ]] || die SITE_ENV_IMAGE_OUTSIDE_CENTRAL_ROOT
[[ "${site[KSC_COURSE_RELEASE]}" == "$central_root"/* ]] || die SITE_ENV_COURSE_OUTSIDE_CENTRAL_ROOT
[[ "${site[KSC_IMAGE_SHA256]}" =~ ^[0-9a-f]{64}$ ]] || die SITE_ENV_IMAGE_SHA_INVALID

require_admin_file() {
    local path=$1 label=$2 expected_kind=${3:-file} resolved owner mode
    [[ "$path" == "$central_root"/* && ! -L "$path" ]] || die "${label}_PATH_NOT_SAFE"
    if [[ "$expected_kind" == directory ]]; then
        [[ -d "$path" ]] || die "${label}_NOT_FOUND"
    else
        [[ -f "$path" ]] || die "${label}_NOT_FOUND"
    fi
    resolved="$(readlink -f "$path")" || die "${label}_RESOLVE_FAILED"
    [[ "$resolved" == "$(readlink -f "$central_root")"/* ]] || die "${label}_OUTSIDE_CENTRAL_ROOT"
    owner="$(stat -c '%u' "$path")" || die "${label}_STAT_FAILED"
    mode="$(stat -c '%a' "$path")" || die "${label}_STAT_FAILED"
    [[ "$owner" == "$central_uid" ]] || die "${label}_OWNER_MISMATCH"
    [[ "$mode" =~ ^[0-7]{3,4}$ ]] || die "${label}_MODE_INVALID"
    (( (8#$mode & 8#022) == 0 )) || die "${label}_WRITABLE_BY_USER"
    if [[ "$expected_kind" == directory ]]; then
        (( (8#$mode & 8#005) == 8#005 )) || die "${label}_NOT_USER_ACCESSIBLE"
    else
        (( (8#$mode & 8#004) == 8#004 )) || die "${label}_NOT_USER_READABLE"
    fi
}

require_trusted_executable() {
    local path=$1 label=$2 resolved owner mode parent
    [[ "$path" == /* && ! -L "$path" && -f "$path" && -x "$path" ]] || \
        die "${label}_NOT_SAFE_OR_EXECUTABLE"
    resolved="$(readlink -f "$path")" || die "${label}_RESOLVE_FAILED"
    [[ "$resolved" == "$path" ]] || die "${label}_PATH_NOT_CANONICAL"
    owner="$(stat -c '%u' "$path")" || die "${label}_STAT_FAILED"
    mode="$(stat -c '%a' "$path")" || die "${label}_STAT_FAILED"
    # KISTI's exact system Apptainer may be owned by a platform service
    # account rather than root. Trust that one pinned path only after its
    # canonical file and every parent are proven non-writable by ordinary users.
    if [[ "$path" != "$trusted_system_apptainer" ]]; then
        [[ "$owner" == 0 || "$owner" == "$central_uid" ]] || die "${label}_OWNER_MISMATCH"
    fi
    [[ "$mode" =~ ^[0-7]{3,4}$ ]] || die "${label}_MODE_INVALID"
    (( (8#$mode & 8#6000) == 0 )) || die "${label}_SETID_NOT_ALLOWED"
    (( (8#$mode & 8#022) == 0 )) || die "${label}_WRITABLE_BY_USER"
    (( (8#$mode & 8#005) == 8#005 )) || die "${label}_NOT_USER_EXECUTABLE"
    parent="$(dirname -- "$resolved")"
    while [[ "$parent" != / ]]; do
        mode="$(stat -c '%a' "$parent")" || die "${label}_PARENT_STAT_FAILED"
        [[ "$mode" =~ ^[0-7]{3,4}$ ]] || die "${label}_PARENT_MODE_INVALID"
        (( (8#$mode & 8#022) == 0 )) || die "${label}_PARENT_WRITABLE_BY_USER"
        (( (8#$mode & 8#001) == 8#001 )) || die "${label}_PARENT_NOT_TRAVERSABLE"
        parent="$(dirname -- "$parent")"
    done
}

require_admin_file "${site[KSC_IMAGE]}" SIF
require_admin_file "${site[KSC_COURSE_RELEASE]}" COURSE_RELEASE directory
require_trusted_executable "${site[KSC_APPTAINER]}" APPTAINER
printf 'VERIFYING_SIF_SHA256=%s\n' "${site[KSC_IMAGE]}"
actual_sif_sha="$(sha256sum "${site[KSC_IMAGE]}" | awk '{print $1}')" || die SIF_SHA_CHECK_FAILED
[[ "$actual_sif_sha" == "${site[KSC_IMAGE_SHA256]}" ]] || die SIF_SHA_MISMATCH

for source_name in ksc2026 start-jupyter session-controller.py jupyter-job.sh; do
    [[ -f "$source_dir/$source_name" && ! -L "$source_dir/$source_name" ]] || die "SOURCE_MISSING_${source_name}"
    [[ "$(stat -c '%u' "$source_dir/$source_name")" == "$central_uid" ]] || die "SOURCE_OWNER_MISMATCH_${source_name}"
    not_group_world_writable "$source_dir/$source_name" || die "SOURCE_WRITABLE_${source_name}"
done
bash -n "$source_dir/ksc2026" "$source_dir/start-jupyter" "$source_dir/jupyter-job.sh"
runtime_python="$(command -v python3)"
if ! "$runtime_python" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 9) else 1)' >/dev/null 2>&1; then
    if ! type module >/dev/null 2>&1; then
        for init_script in /etc/profile.d/modules.sh /usr/share/Modules/init/bash /etc/profile; do
            if [[ -r "$init_script" ]]; then
                # shellcheck disable=SC1090
                source "$init_script"
                type module >/dev/null 2>&1 && break
            fi
        done
    fi
    type module >/dev/null 2>&1 || die PYTHON_MODULE_SYSTEM_UNAVAILABLE
    module load cray-python/3.11.7 || die PYTHON_MODULE_LOAD_FAILED
    runtime_python="$(command -v python3)"
fi
"$runtime_python" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 9) else 1)' || die PYTHON_39_REQUIRED
"$runtime_python" -B -c '
import importlib.util
import pathlib
import sys
source_dir = pathlib.Path(sys.argv[1])
site_env = pathlib.Path(sys.argv[2])
sys.path.insert(0, str(source_dir))
spec = importlib.util.spec_from_file_location("ksc2026_session_controller", source_dir / "session-controller.py")
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)
module.parse_site_config(site_env)
' "$source_dir" "$site_env" || die ACTUAL_CONTROLLER_SITE_CONFIG_REJECTED
"$runtime_python" -B -c '
import importlib.util
import pathlib
import sys
source_dir = pathlib.Path(sys.argv[1])
site_env = pathlib.Path(sys.argv[2])
central_owner = sys.argv[3]
sys.path.insert(0, str(source_dir))
spec = importlib.util.spec_from_file_location("ksc2026_release_check", source_dir / "session-controller.py")
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)
config = module.parse_site_config(site_env)
module.read_course(config, site_env, central_owner)
' "$source_dir" "$site_env" "$central_owner" || die ACTUAL_CONTROLLER_COURSE_RELEASE_REJECTED
"$runtime_python" -B -c 'import pathlib, sys; [compile(pathlib.Path(p).read_text(encoding="utf-8"), p, "exec") for p in sys.argv[1:]]' \
    "$source_dir/session-controller.py" || die PYTHON_SOURCE_INVALID

entrypoint_source="$source_dir/ksc2026"
entrypoint_target="$central_root/bin/ksc2026"
entrypoint_mode=0755
entrypoint_action=INSTALL
entrypoint_sha="$(sha256sum "$entrypoint_source" | awk '{print $1}')"
if [[ -e "$entrypoint_target" || -L "$entrypoint_target" ]]; then
    [[ -f "$entrypoint_target" && ! -L "$entrypoint_target" ]] || \
        die CENTRAL_ENTRYPOINT_NOT_SAFE
    [[ "$(stat -c '%u:%a:%h' "$entrypoint_target")" == \
       "$central_uid:${entrypoint_mode#0}:1" ]] || \
        die CENTRAL_ENTRYPOINT_METADATA_MISMATCH
    cmp -s "$entrypoint_source" "$entrypoint_target" || \
        die CENTRAL_ENTRYPOINT_IMMUTABLE_CONTENT_MISMATCH
    entrypoint_action=ALREADY_CURRENT
fi
printf 'CENTRAL_SOURCE_SHA256=%s SOURCE=%s\n' "$entrypoint_sha" "$entrypoint_source"
printf 'CENTRAL_ACTION=%s TARGET=%s\n' "$entrypoint_action" "$entrypoint_target"

declare -a source_paths=(
    "$source_dir/start-jupyter"
    "$source_dir/session-controller.py"
    "$source_dir/jupyter-job.sh"
    "$site_env"
)
declare -a target_paths=(
    "$central_root/bin/start-jupyter"
    "$central_root/bin/session-controller.py"
    "$central_root/slurm/jupyter-job.sh"
    "$central_root/config/site.env"
)
declare -a target_modes=(0755 0644 0755 0644)

for directory in "$central_root/bin" "$central_root/config" "$central_root/slurm"; do
    if [[ -e "$directory" || -L "$directory" ]]; then
        [[ -d "$directory" && ! -L "$directory" && \
           "$(stat -c '%u:%a' "$directory")" == "$central_uid:755" ]] || die CENTRAL_DIRECTORY_NOT_SAFE
    fi
done

central_changes=0
[[ "$entrypoint_action" == ALREADY_CURRENT ]] || (( central_changes += 1 ))
for index in "${!source_paths[@]}"; do
    source_path=${source_paths[$index]}; target_path=${target_paths[$index]}; target_mode=${target_modes[$index]}
    source_sha="$(sha256sum "$source_path" | awk '{print $1}')"
    action=INSTALL
    if [[ -e "$target_path" || -L "$target_path" ]]; then
        [[ -f "$target_path" && ! -L "$target_path" ]] || die "CENTRAL_TARGET_NOT_SAFE_${index}"
        [[ "$(stat -c '%u:%a:%h' "$target_path")" == "$central_uid:${target_mode#0}:1" ]] || die "CENTRAL_TARGET_METADATA_MISMATCH_${index}"
        if cmp -s "$source_path" "$target_path"; then action=ALREADY_CURRENT; else action=UPDATE; fi
    fi
    printf 'CENTRAL_SOURCE_SHA256=%s SOURCE=%s\n' "$source_sha" "$source_path"
    printf 'CENTRAL_ACTION=%s TARGET=%s\n' "$action" "$target_path"
    [[ "$action" == ALREADY_CURRENT ]] || (( central_changes += 1 ))
done

if (( apply == 1 && central_changes > 0 )); then
    command -v squeue >/dev/null 2>&1 || die MISSING_COMMAND_squeue
    active_sessions="$(
        squeue --noheader --states=PENDING,CONFIGURING,RUNNING,COMPLETING,SUSPENDED \
            --format='%j' | awk '/^ksc26-jlab-/{count++} END{print count+0}'
    )" || die ACTIVE_SESSION_CHECK_FAILED
    [[ "$active_sessions" == 0 ]] || die ACTIVE_SESSIONS_MUST_STOP_BEFORE_UPDATE
fi

if (( apply == 1 )); then
    for directory in "$central_root/bin" "$central_root/config" "$central_root/slurm"; do
        if [[ ! -e "$directory" && ! -L "$directory" ]]; then
            install -d -m 0755 "$directory"
        fi
        [[ -d "$directory" && ! -L "$directory" && "$(stat -c '%u:%a' "$directory")" == "$central_uid:755" ]] || die CENTRAL_DIRECTORY_NOT_SAFE
    done
    if [[ "$entrypoint_action" == INSTALL ]]; then
        entrypoint_tmp="$(mktemp "$central_root/bin/.ksc2026-entrypoint.XXXXXXXX")"
        install -m "$entrypoint_mode" "$entrypoint_source" "$entrypoint_tmp"
        [[ "$(sha256sum "$entrypoint_tmp" | awk '{print $1}')" == "$entrypoint_sha" ]] || \
            die CENTRAL_ENTRYPOINT_TEMP_SHA_MISMATCH
        mv -- "$entrypoint_tmp" "$entrypoint_target"
    fi
    [[ -f "$entrypoint_target" && ! -L "$entrypoint_target" && \
       "$(stat -c '%u:%a:%h' "$entrypoint_target")" == \
       "$central_uid:${entrypoint_mode#0}:1" ]] || \
        die CENTRAL_ENTRYPOINT_POSTCHECK_METADATA_MISMATCH
    cmp -s "$entrypoint_source" "$entrypoint_target" || \
        die CENTRAL_ENTRYPOINT_POSTCHECK_CONTENT_MISMATCH

    for index in "${!source_paths[@]}"; do
        source_path=${source_paths[$index]}; target_path=${target_paths[$index]}; target_mode=${target_modes[$index]}
        if [[ ! -e "$target_path" ]] || ! cmp -s "$source_path" "$target_path"; then
            target_dir="$(dirname -- "$target_path")"
            tmp="$(mktemp "$target_dir/.ksc2026-install.XXXXXXXX")"
            install -m "$target_mode" "$source_path" "$tmp"
            [[ "$(sha256sum "$tmp" | awk '{print $1}')" == "$(sha256sum "$source_path" | awk '{print $1}')" ]] || die CENTRAL_TEMP_SHA_MISMATCH
            mv -- "$tmp" "$target_path"
        fi
        [[ -f "$target_path" && ! -L "$target_path" && \
           "$(stat -c '%u:%a:%h' "$target_path")" == "$central_uid:${target_mode#0}:1" ]] || die CENTRAL_POSTCHECK_METADATA_MISMATCH
        cmp -s "$source_path" "$target_path" || die CENTRAL_POSTCHECK_CONTENT_MISMATCH
    done
fi

printf 'KSC_INSTALL_MODE=%s\n' "$([[ $apply == 1 ]] && printf APPLY || printf DRY_RUN)"
printf 'KSC_CENTRAL_CHANGES=%s\n' "$central_changes"
printf 'KSC_SHARED_COMMAND=%s\n' "$central_root/bin/ksc2026"
printf 'KSC_INSTALL_COMPLETE=yes\n'
