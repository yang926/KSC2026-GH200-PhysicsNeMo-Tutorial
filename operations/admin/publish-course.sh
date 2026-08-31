#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
#
# Publish one exact, validated Git commit as a shared read-only course release.
# Run only on the internet-connected login node, never on a compute node.

set -Eeuo pipefail
set -f
umask 077
export LC_ALL=C

usage() {
    cat <<'EOF'
사용법: publish-course.sh [--root /scratch/hackathon/ksc2026] [--site-env /secure/operator/site.env] [--ref main] [--commit 40자리_SHA] [--frozen-commit 40자리_SHA]

--commit을 지정하면 해당 commit이 --ref branch의 이력에 포함되는지도 확인합니다.
--frozen-commit을 지정하면 요청 commit과 일치할 때만 게시합니다. 이 값은
참가자 runtime site.env에 넣지 않고 운영자가 명령행으로만 전달합니다.
첫 게시에서는 --site-env로 설치 전 비공개 설정 파일을 지정할 수 있습니다.
기존 release와 참가자의 작업 폴더는 삭제하지 않습니다.
EOF
}

die() {
    printf 'KSC2026 강의자료 게시 오류: %s\n' "$*" >&2
    exit 1
}

canonical_parent=/scratch/hackathon
canonical_root=/scratch/hackathon/ksc2026
install_root=$canonical_root
site_env_override=""
ref_override=""
commit_override=""
frozen_commit=""
while (( $# > 0 )); do
    case "$1" in
        --root)
            (( $# >= 2 )) || { usage >&2; exit 2; }
            install_root="$2"
            shift 2
            ;;
        --site-env)
            (( $# >= 2 )) || { usage >&2; exit 2; }
            site_env_override="$2"
            shift 2
            ;;
        --ref)
            (( $# >= 2 )) || { usage >&2; exit 2; }
            ref_override="$2"
            shift 2
            ;;
        --commit)
            (( $# >= 2 )) || { usage >&2; exit 2; }
            commit_override="$2"
            shift 2
            ;;
        --frozen-commit)
            (( $# >= 2 )) || { usage >&2; exit 2; }
            frozen_commit="$2"
            shift 2
            ;;
        -h|--help) usage; exit 0 ;;
        *) printf '알 수 없는 옵션입니다: %s\n' "$1" >&2; usage >&2; exit 2 ;;
    esac
done

[[ "$install_root" == "$canonical_root" ]] ||
    die "공유 root는 확인된 경로만 사용할 수 있습니다: $canonical_root"
[[ -z "$commit_override" || "$commit_override" =~ ^[a-f0-9]{40}$ ]] ||
    die "--commit에는 정확한 40자리 소문자 SHA가 필요합니다"
[[ -z "$frozen_commit" || "$frozen_commit" =~ ^[a-f0-9]{40}$ ]] ||
    die "--frozen-commit 형식이 올바르지 않습니다"

for required_command in awk bash chmod dirname git grep id install mv tar python3 mktemp \
    sha256sum find sort xargs stat flock readlink; do
    command -v "$required_command" >/dev/null 2>&1 ||
        die "필수 명령을 찾을 수 없습니다: $required_command"
done
stat -c '%u:%g:%a' / >/dev/null 2>&1 || die "GNU stat이 필요합니다"
readlink -f / >/dev/null 2>&1 || die "GNU readlink가 필요합니다"

actor_uid="$(id -u)"
[[ "$actor_uid" =~ ^[0-9]+$ && "$actor_uid" != 0 ]] ||
    die "중앙 owner의 일반 계정으로만 게시할 수 있습니다. root/sudo를 사용하지 마세요"
[[ -d "$canonical_parent" && ! -L "$canonical_parent" ]] ||
    die "확인된 공용 parent가 일반 디렉터리가 아닙니다: $canonical_parent"
[[ "$(readlink -f "$canonical_parent")" == "$canonical_parent" ]] ||
    die "공용 parent가 canonical 경로가 아닙니다: $canonical_parent"
[[ "$(stat -c '%u:%g:%a' "$canonical_parent")" == "0:0:1777" ]] ||
    die "공용 parent는 root:root mode 1777이어야 합니다: $canonical_parent"
[[ -d "$install_root" && ! -L "$install_root" ]] ||
    die "중앙 owner가 먼저 mode 0755 공유 root를 생성해야 합니다: $install_root"
[[ "$(readlink -f "$install_root")" == "$install_root" ]] ||
    die "공유 root가 canonical 경로가 아닙니다: $install_root"
[[ "$(stat -c '%u:%a' "$install_root")" == "$actor_uid:755" ]] ||
    die "공유 root는 현재 중앙 owner 소유 mode 0755여야 합니다: $install_root"

site_env="${site_env_override:-${install_root}/config/site.env}"
[[ "$site_env" == /* && "$site_env" != *$'\n'* ]] ||
    die "site.env는 안전한 절대 경로여야 합니다: $site_env"
[[ -f "$site_env" && ! -L "$site_env" && -r "$site_env" ]] ||
    die "사이트 설정은 읽을 수 있는 regular file이어야 합니다: $site_env"
[[ "$(stat -c '%u' "$site_env")" == "$actor_uid" ]] ||
    die "site.env는 현재 중앙 owner 소유여야 합니다: $site_env"
site_mode="$(stat -c '%a' "$site_env" 2>/dev/null || true)"
[[ "$site_mode" =~ ^[0-7]+$ ]] || die "site.env 권한을 확인할 수 없습니다"
(( (8#$site_mode & 0022) == 0 )) || die "site.env를 group/other가 수정할 수 있습니다: mode=$site_mode"
declare -A site=()
allowed_site_keys=' KSC_SHARED_ROOT KSC_LOGIN_HOST KSC_PARTITION KSC_JOB_COMMENT KSC_GRES_NAME KSC_TIME_LIMIT KSC_READY_TIMEOUT KSC_APPTAINER KSC_IMAGE KSC_IMAGE_SHA256 KSC_SIF_SHA256 KSC_COURSE_RELEASE_ROOT KSC_COURSE_RELEASE KSC_COURSE_REPOSITORY KSC_COURSE_REF KSC_COURSE_SOURCE KSC_RUNTIME_COMPATIBILITY KSC_JOB_SCRIPT KSC_STATE_ROOT KSC_WORKSPACE_ROOT KSC_LOG_ROOT KSC_CPUS_PER_TASK KSC_MEMORY '
line_number=0
while IFS= read -r raw || [[ -n "$raw" ]]; do
    (( line_number += 1 ))
    [[ "$raw" != *$'\r'* ]] || die "site.env ${line_number}행에 CR 문자가 있습니다"
    line="${raw#"${raw%%[![:space:]]*}"}"
    line="${line%"${line##*[![:space:]]}"}"
    [[ -n "$line" && "${line:0:1}" != '#' ]] || continue
    [[ "$line" == *=* ]] || die "site.env ${line_number}행에 '='가 없습니다"
    key="${line%%=*}"
    value="${line#*=}"
    [[ "$key" =~ ^KSC_[A-Z0-9_]+$ && "$allowed_site_keys" == *" $key "* ]] ||
        die "site.env ${line_number}행에 허용되지 않은 항목이 있습니다: $key"
    [[ -z "${site[$key]+x}" ]] || die "site.env 항목이 중복됩니다: $key"
    [[ "$value" != *'`'* && "$value" != *'$'* ]] ||
        die "site.env 값을 셸 표현식으로 사용할 수 없습니다: $key"
    site[$key]="$value"
done <"$site_env"

repo_url="${site[KSC_COURSE_REPOSITORY]:-https://github.com/yang926/KSC2026-GH200-PhysicsNeMo-Tutorial.git}"
course_ref="${ref_override:-${site[KSC_COURSE_REF]:-main}}"
release_root="${site[KSC_COURSE_RELEASE_ROOT]:-${install_root}/course-releases}"
current_link="${site[KSC_COURSE_SOURCE]:-${install_root}/course-current}"
runtime_compatibility="${site[KSC_RUNTIME_COMPATIBILITY]:-ksc2026-gh200-physicsnemo-25.11-arm64-v1}"
# The current shared controller calls the immutable runtime path
# KSC_IMAGE, while the original publisher called it KSC_SIF.  Accept either
# SHA key so one operator-owned site.env can drive both tools.
site_sif_sha="${site[KSC_SIF_SHA256]:-${site[KSC_IMAGE_SHA256]:-}}"
[[ -z "${site[KSC_SHARED_ROOT]:-}" || "${site[KSC_SHARED_ROOT]}" == "$install_root" ]] ||
    die "site.env의 KSC_SHARED_ROOT가 확인된 공유 root와 다릅니다"
if [[ -n "${site[KSC_SIF_SHA256]:-}" && -n "${site[KSC_IMAGE_SHA256]:-}" ]]; then
    [[ "${site[KSC_SIF_SHA256]}" == "${site[KSC_IMAGE_SHA256]}" ]] ||
        die "site.env의 SIF SHA256 두 값이 서로 다릅니다"
fi

[[ "$repo_url" =~ ^https://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+(\.git)?$ ]] ||
    die "공개 GitHub HTTPS 저장소만 사용할 수 있습니다: $repo_url"
[[ "$course_ref" =~ ^[A-Za-z0-9._/-]+$ && "$course_ref" != -* &&
   "${course_ref: -1}" != "/" && "$course_ref" != *..* && "$course_ref" != *"//"* ]] ||
    die "안전한 GitHub branch 이름이 아닙니다: $course_ref"
[[ "$site_sif_sha" =~ ^[a-f0-9]{64}$ ]] ||
    die "site.env에 실제 SIF의 KSC_SIF_SHA256 64자리 값이 필요합니다"
[[ "$runtime_compatibility" =~ ^[A-Za-z0-9._-]+$ ]] ||
    die "runtime compatibility 값이 올바르지 않습니다"

[[ "$release_root" == "${install_root}/course-releases" ]] ||
    die "강의 release root는 확인된 고정 경로여야 합니다: $release_root"
[[ "$current_link" == "${install_root}/course-current" ]] ||
    die "강의 current 포인터는 확인된 고정 경로여야 합니다: $current_link"

admin_root="${install_root}/admin"
mirror_dir="${admin_root}/course-repository.git"
require_owned_directory() {
    local path=$1 label=$2
    if [[ ! -e "$path" && ! -L "$path" ]]; then
        install -d -m 0755 "$path"
    fi
    [[ -d "$path" && ! -L "$path" ]] || die "$label 경로가 일반 디렉터리가 아닙니다: $path"
    [[ "$(readlink -f "$path")" == "$path" ]] || die "$label 경로가 canonical 경로가 아닙니다: $path"
    [[ "$(stat -c '%u:%a' "$path")" == "$actor_uid:755" ]] ||
        die "$label 경로는 중앙 owner 소유 mode 0755여야 합니다: $path"
}
require_owned_directory "$admin_root" "관리"

deployment_lock="${admin_root}/deployment.lock"
if [[ ! -e "$deployment_lock" && ! -L "$deployment_lock" ]]; then
    # noclobber makes first creation atomic when two owner processes start at once.
    # The subshell umask creates the participant-readable, owner-only-writable
    # lock at its final mode without a chmod race.
    ( umask 022; set -o noclobber; : >"$deployment_lock" ) 2>/dev/null || true
fi
[[ -f "$deployment_lock" && ! -L "$deployment_lock" &&
   "$(stat -c '%u:%a:%h' "$deployment_lock")" == "$actor_uid:644:1" ]] ||
    die "중앙 배포 lock이 안전하지 않습니다: $deployment_lock"
exec 9<>"$deployment_lock"
flock -x -n 9 || die "다른 중앙 배포 또는 강의자료 게시 작업이 실행 중입니다"
require_owned_directory "$release_root" "강의 release"

temporary_parent=""
validation_dir=""
staging_dir=""
payload_manifest_tmp=""
current_tmp=""
site_env_tmp=""
cleanup() {
    local saved_status=$?
    set +e
    [[ -z "$current_tmp" || ! -L "$current_tmp" ]] || unlink "$current_tmp"
    if [[ -n "$staging_dir" && -d "$staging_dir" && "$staging_dir" == "${release_root}/.staging."* ]]; then
        rm -rf -- "$staging_dir"
    fi
    if [[ -n "$validation_dir" && -d "$validation_dir" && "$validation_dir" == "${admin_root}/.course-validation."* ]]; then
        rm -rf -- "$validation_dir"
    fi
    if [[ -n "$temporary_parent" && -d "$temporary_parent" && "$temporary_parent" == "${admin_root}/.course-mirror."* ]]; then
        rm -rf -- "$temporary_parent"
    fi
    [[ -z "$payload_manifest_tmp" || ! -f "$payload_manifest_tmp" ]] || unlink "$payload_manifest_tmp"
    [[ -z "$site_env_tmp" || ! -f "$site_env_tmp" ]] || unlink "$site_env_tmp"
    flock -u 9 >/dev/null 2>&1 || true
    return "$saved_status"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM HUP

if [[ ! -d "$mirror_dir" ]]; then
    [[ ! -e "$mirror_dir" && ! -L "$mirror_dir" ]] ||
        die "기존 mirror 경로가 안전하지 않습니다: $mirror_dir"
    temporary_parent="$(mktemp -d "${admin_root}/.course-mirror.XXXXXX")"
    git clone --mirror "$repo_url" "${temporary_parent}/repository.git"
    mv "${temporary_parent}/repository.git" "$mirror_dir"
    rmdir "$temporary_parent"
    temporary_parent=""
else
    [[ ! -L "$mirror_dir" && "$(readlink -f "$mirror_dir")" == "$mirror_dir" &&
       "$(stat -c '%u' "$mirror_dir")" == "$actor_uid" ]] ||
        die "기존 mirror의 경로 또는 owner가 안전하지 않습니다: $mirror_dir"
    mirror_mode="$(stat -c '%a' "$mirror_dir")"
    [[ "$mirror_mode" =~ ^[0-7]+$ ]] && (( (8#$mirror_mode & 0022) == 0 )) ||
        die "기존 mirror를 group/other가 수정할 수 있습니다: $mirror_dir"
    [[ -f "${mirror_dir}/HEAD" ]] || die "기존 mirror가 Git 저장소가 아닙니다: $mirror_dir"
    configured_remote="$(git --git-dir="$mirror_dir" remote get-url origin)"
    [[ "$configured_remote" == "$repo_url" ]] ||
        die "기존 mirror origin이 설정과 다릅니다: $configured_remote"
fi

git --git-dir="$mirror_dir" fetch --prune origin \
    "+refs/heads/${course_ref}:refs/remotes/origin/${course_ref}"
branch_tip="$(git --git-dir="$mirror_dir" rev-parse --verify "refs/remotes/origin/${course_ref}^{commit}")"
if [[ -n "$commit_override" ]]; then
    git --git-dir="$mirror_dir" cat-file -e "${commit_override}^{commit}" 2>/dev/null ||
        die "지정한 commit을 mirror에서 찾을 수 없습니다: $commit_override"
    git --git-dir="$mirror_dir" merge-base --is-ancestor "$commit_override" "$branch_tip" ||
        die "지정한 commit은 origin/$course_ref 이력에 포함되지 않습니다"
    course_commit="$(git --git-dir="$mirror_dir" rev-parse "${commit_override}^{commit}")"
else
    course_commit="$branch_tip"
fi
[[ "$course_commit" =~ ^[a-f0-9]{40}$ ]] || die "Git commit 형식이 올바르지 않습니다"
[[ -z "$frozen_commit" || "$course_commit" == "$frozen_commit" ]] ||
    die "행사 freeze commit과 다릅니다: requested=$course_commit frozen=$frozen_commit"

release_dir="${release_root}/${course_commit}"

verify_release() {
    local directory="$1"
    local revision compatibility repository compatible count_expected count_actual
    [[ -d "$directory" && ! -L "$directory" ]] || return 1
    revision="$(tr -d '\r\n' <"${directory}/.ksc2026-course-revision" 2>/dev/null || true)"
    compatibility="$(tr -d '\r\n' <"${directory}/.ksc2026-runtime-compatibility" 2>/dev/null || true)"
    repository="$(tr -d '\r\n' <"${directory}/.ksc2026-course-repository" 2>/dev/null || true)"
    compatible="$(tr -d '\r\n' <"${directory}/.ksc2026-compatible-sif-sha256" 2>/dev/null || true)"
    [[ "$revision" == "$course_commit" && "$compatibility" == "$runtime_compatibility" &&
       "$repository" == "$repo_url" && "$compatible" == "$site_sif_sha" ]] || return 1
    [[ -f "${directory}/.ksc2026-payload.sha256" && ! -L "${directory}/.ksc2026-payload.sha256" ]] || return 1
    (cd "$directory" && sha256sum --check --strict .ksc2026-payload.sha256 >/dev/null) || return 1
    ! find "$directory" -type l -print -quit | grep -q . || return 1
    ! find "$directory" -perm /022 -print -quit | grep -q . || return 1
    ! find "$directory" -type d ! -perm -0555 -print -quit | grep -q . || return 1
    ! find "$directory" -type f ! -perm -0444 -print -quit | grep -q . || return 1
    count_expected="$(wc -l <"${directory}/.ksc2026-payload.sha256" | tr -d ' ')"
    count_actual="$(find "$directory" -type f | wc -l | tr -d ' ')"
    [[ "$count_actual" == "$((10#$count_expected + 5))" ]] || return 1
}

if [[ -e "$release_dir" ]]; then
    verify_release "$release_dir" ||
        die "기존 release의 내용·권한·SHA256 manifest가 계약과 다릅니다: $release_dir"
    printf '이미 검증된 immutable release를 재사용합니다: %s\n' "$course_commit"
else
    validation_dir="$(mktemp -d "${admin_root}/.course-validation.XXXXXX")"
    git --git-dir="$mirror_dir" archive --format=tar "$course_commit" | tar -xf - -C "$validation_dir"
    (
        cd "$validation_dir"
        while IFS= read -r script; do bash -n "$script"; done < <(find operations container -type f -name '*.sh' -o -type f -name 'ksc2026-start' -o -type f -name 'start-jupyter' -o -type f -name 'stop-jupyter' -o -type f -name 'preflight-gh200')
        python3 tools/validate_course.py
    )

    mapfile -t manifest_lines < <(python3 - "${validation_dir}/course-release.json" <<'PY'
import json
import re
import sys
from pathlib import Path, PurePosixPath

data = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
if data.get("schema_version") != 2:
    raise SystemExit("course-release.json schema_version은 2여야 합니다")
compatibility = data.get("runtime_compatibility")
hashes = data.get("compatible_sif_sha256")
paths = data.get("participant_paths")
if not isinstance(compatibility, str):
    raise SystemExit("runtime_compatibility 문자열이 필요합니다")
if not isinstance(hashes, list) or not hashes:
    raise SystemExit("compatible_sif_sha256 목록이 필요합니다")
if any(not isinstance(value, str) or not re.fullmatch(r"[a-f0-9]{64}", value) for value in hashes):
    raise SystemExit("compatible_sif_sha256 형식이 올바르지 않습니다")
if not isinstance(paths, list) or not paths:
    raise SystemExit("participant_paths 목록이 필요합니다")
seen = set()
for value in paths:
    if not isinstance(value, str) or not value or "\\" in value:
        raise SystemExit("participant_paths에는 안전한 상대 경로만 사용할 수 있습니다")
    parts = PurePosixPath(value).parts
    if value.startswith("/") or value == "." or any(part in ("", ".", "..") for part in parts):
        raise SystemExit(f"안전하지 않은 participant path: {value}")
    if value in seen:
        raise SystemExit(f"중복 participant path: {value}")
    seen.add(value)
print("COMPAT:" + compatibility)
for value in hashes:
    print("SIF:" + value)
for value in paths:
    print("PATH:" + value)
PY
)
    manifest_compatibility=""
    compatible_hashes=()
    participant_paths=()
    for line in "${manifest_lines[@]}"; do
        case "$line" in
            COMPAT:*) manifest_compatibility="${line#COMPAT:}" ;;
            SIF:*) compatible_hashes+=("${line#SIF:}") ;;
            PATH:*) participant_paths+=("${line#PATH:}") ;;
            *) die "course-release.json 파서가 알 수 없는 값을 반환했습니다" ;;
        esac
    done
    [[ "$manifest_compatibility" == "$runtime_compatibility" ]] ||
        die "강의자료와 사이트 runtime compatibility가 다릅니다"
    printf '%s\n' "${compatible_hashes[@]}" | grep -Fqx "$site_sif_sha" ||
        die "강의자료가 실제 사이트 SIF SHA256을 허용하지 않습니다: $site_sif_sha"

    staging_dir="$(mktemp -d "${release_root}/.staging.XXXXXX")"
    git --git-dir="$mirror_dir" archive --format=tar "$course_commit" -- "${participant_paths[@]}" |
        tar -xf - -C "$staging_dir"
    python3 "${validation_dir}/tools/validate_participant_release.py" "$staging_dir"

    payload_manifest_tmp="$(mktemp "${admin_root}/.payload-sha256.XXXXXX")"
    (
        cd "$staging_dir"
        find . -type f -print0 | LC_ALL=C sort -z | xargs -0 sha256sum
    ) >"$payload_manifest_tmp"
    install -m 0444 "$payload_manifest_tmp" "${staging_dir}/.ksc2026-payload.sha256"
    unlink "$payload_manifest_tmp"
    payload_manifest_tmp=""

    printf '%s\n' "$course_commit" >"${staging_dir}/.ksc2026-course-revision"
    printf '%s\n' "$runtime_compatibility" >"${staging_dir}/.ksc2026-runtime-compatibility"
    printf '%s\n' "$repo_url" >"${staging_dir}/.ksc2026-course-repository"
    printf '%s\n' "$site_sif_sha" >"${staging_dir}/.ksc2026-compatible-sif-sha256"
    chmod -R a+rX,a-w "$staging_dir"
    verify_release "$staging_dir" || die "게시 직전 release readback 검증에 실패했습니다"
    mv "$staging_dir" "$release_dir"
    staging_dir=""

    rm -rf -- "$validation_dir"
    validation_dir=""
    printf '새 immutable release를 게시했습니다: %s\n' "$course_commit"
fi

if [[ -e "$current_link" && ! -L "$current_link" ]]; then
    die "current 경로가 심볼릭 링크가 아니므로 바꾸지 않습니다: $current_link"
fi
current_tmp="${current_link}.new.$$"
[[ ! -e "$current_tmp" && ! -L "$current_tmp" ]] || die "임시 current 링크가 이미 존재합니다"
ln -s "$release_dir" "$current_tmp"
mv -Tf "$current_tmp" "$current_link"
current_tmp=""

# Sessions intentionally consume an exact immutable release path, never the
# mutable course-current symlink.  Activate the newly published exact path
# atomically so that the next explicit --refresh sees it.
course_release_activated=0
course_release_key_count="$(grep -c '^KSC_COURSE_RELEASE=' "$site_env" || true)"
[[ "$course_release_key_count" =~ ^[0-9]+$ ]] || die "KSC_COURSE_RELEASE 항목 수를 확인할 수 없습니다"
if (( course_release_key_count > 1 )); then
    die "site.env의 KSC_COURSE_RELEASE 항목이 중복됩니다"
elif (( course_release_key_count == 1 )); then
    site_dir="$(dirname -- "$site_env")"
    [[ -d "$site_dir" && ! -L "$site_dir" ]] || die "site.env 폴더가 안전하지 않습니다: $site_dir"
    site_dir_mode="$(stat -c '%a' "$site_dir")"
    [[ "$site_dir_mode" =~ ^[0-7]+$ ]] || die "site.env 폴더 권한을 확인할 수 없습니다"
    (( (8#$site_dir_mode & 0022) == 0 )) || die "site.env 폴더를 group/other가 수정할 수 있습니다"
    site_uid="$(stat -c '%u' "$site_env")"
    current_uid="$(id -u)"
    [[ "$current_uid" == "$site_uid" ]] || \
        die "현재 중앙 owner만 참가자 release를 활성화할 수 있습니다"
    site_env_tmp="$(mktemp "${site_dir}/.site.env.course.XXXXXX")"
    awk -v value="KSC_COURSE_RELEASE=${release_dir}" \
        'BEGIN {changed=0} /^KSC_COURSE_RELEASE=/ {print value; changed++; next} {print} END {if (changed != 1) exit 42}' \
        "$site_env" >"$site_env_tmp" || die "site.env의 참가자 release 경로를 갱신하지 못했습니다"
    chmod "$site_mode" "$site_env_tmp"
    mv -f -- "$site_env_tmp" "$site_env"
    site_env_tmp=""
    [[ "$(grep '^KSC_COURSE_RELEASE=' "$site_env")" == "KSC_COURSE_RELEASE=${release_dir}" ]] || \
        die "site.env 강의 release 갱신 후 readback에 실패했습니다"
    course_release_activated=1
fi

printf 'KSC2026_COURSE_PUBLISHED=1\n'
printf 'KSC_COURSE_COMMIT=%s\n' "$course_commit"
printf 'KSC_COURSE_RELEASE=%s\n' "$release_dir"
printf 'KSC_SIF_SHA256=%s\n' "$site_sif_sha"
printf 'KSC_COURSE_RELEASE_ACTIVATED=%s\n' "$course_release_activated"
