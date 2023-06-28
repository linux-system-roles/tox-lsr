#!/bin/bash

set -euo pipefail

CONTAINER_OPTS="--privileged --systemd=true --hostname ${CONTAINER_HOSTNAME:-sut}"
CONTAINER_MOUNTS="-v /sys/fs/cgroup:/sys/fs/cgroup"
#CONTAINER_ENTRYPOINT="/usr/sbin/init"
#CONTAINER_IMAGE_NAME=${CONTAINER_IMAGE_NAME:-centos-8}
#CONTAINER_BASE_IMAGE=${CONTAINER_BASE_IMAGE:-quay.io/centos/centos:stream8}
#CONTAINER_IMAGE=${CONTAINER_IMAGE:-lsr-test-$CONTAINER_PLATFORM:latest}
CONTAINER_AGE=${CONTAINER_AGE:-24}  # hours
CONTAINER_TESTS_PATH=${CONTAINER_TESTS_PATH:-"$TOXINIDIR/tests"}
CONTAINER_SKIP_TAGS=${CONTAINER_SKIP_TAGS:---skip-tags tests::no_container}
CONTAINER_CONFIG="$HOME/.config/linux-system-roles.json"

COLLECTION_BASE_PATH="${COLLECTION_BASE_PATH:-$TOX_WORK_DIR}"
export ANSIBLE_COLLECTIONS_PATHS="${ANSIBLE_COLLECTIONS_PATHS:-$COLLECTION_BASE_PATH}"
LOCAL_COLLECTION="${LOCAL_COLLECTION:-fedora/linux_system_roles}"

logit() {
    local level
    level="$1"; shift
    echo ::"$level" "$(date -Isec)" "$@"
}

info() {
    logit info "$@"
}

notice() {
    logit notice "$@"
}

warning() {
    logit warning "$@"
}

error() {
    logit error "$@"
}

install_requirements() {
    local rq save_tar force update coll_path
    # see what capabilities ansible-galaxy has
    if ansible-galaxy collection install --help 2>&1 | grep -q -- --force; then
        force=--force
    fi
    if ansible-galaxy collection install --help 2>&1 | grep -q -- --upgrade; then
        upgrade=--upgrade
    fi
    coll_path="$COLLECTION_BASE_PATH/ansible_collections"
    if [ -d "$coll_path/$LOCAL_COLLECTION" ]; then
        info saving local collection at "$coll_path/$LOCAL_COLLECTION"
        save_tar="$(mktemp)"
        tar cfP "$save_tar" -C "$coll_path" "$LOCAL_COLLECTION"
        trap "rm -f $save_tar" RETURN
    fi
    for rq in meta/requirements.yml meta/collection-requirements.yml; do
        if [ -f "$rq" ]; then
            if [ "$rq" = meta/requirements.yml ]; then
                warning use meta/collection-requirements.yml instead of "$rq"
            fi
            ansible-galaxy collection install ${force:-} ${upgrade:-} -p "$COLLECTION_BASE_PATH" -vv -r "$rq"
        fi
    done
    if [ -n "${save_tar:-}" ] && [ -f "${save_tar:-}" ]; then
        tar xfP "$save_tar" -C "$coll_path" --overwrite
        info restoring local collection at "$coll_path/$LOCAL_COLLECTION"
    fi
}

setup_plugins() {
    if [ "${LSR_CONTAINER_PRETTY:-true}" = true ] || [ "${LSR_CONTAINER_PROFILE:-true}" = true ]; then
        local callback_plugin_dir
        callback_plugin_dir="$TOX_WORK_DIR/callback_plugins"
        if [ ! -d "$callback_plugin_dir" ]; then
            mkdir -p "$callback_plugin_dir"
        fi
        local debug_py
        local profile_py
        debug_py="$callback_plugin_dir/debug.py"
        profile_py="$callback_plugin_dir/profile_tasks.py"
        local need_debug_py
        local need_profile_py
        if [ "${LSR_CONTAINER_PRETTY:-true}" = true ] && [ ! -f "$debug_py" ]; then
            need_debug_py=1
        fi
        if [ "${LSR_CONTAINER_PROFILE:-true}" = true ] && [ ! -f "$profile_py" ]; then
            need_profile_py=1
        fi
        if [ -n "${need_debug_py:-}" ] || [ -n "${need_profile_py:-}" ]; then
            ansible-galaxy collection install -p "$LSR_TOX_ENV_TMP_DIR" -vv ansible.posix
            tmp_debug_py="$LSR_TOX_ENV_TMP_DIR/ansible_collections/ansible/posix/plugins/callback/debug.py"
            tmp_profile_py="$LSR_TOX_ENV_TMP_DIR/ansible_collections/ansible/posix/plugins/callback/profile_tasks.py"
            if [ -n "${need_debug_py:-}" ]; then
                mv "$tmp_debug_py" "$debug_py"
            fi
            if [ -n "${need_profile_py:-}" ]; then
                mv "$tmp_profile_py" "$profile_py"
            fi
            rm -rf "$LSR_TOX_ENV_TMP_DIR/ansible_collections"
        fi
        if [ "${LSR_CONTAINER_PRETTY:-true}" = true ]; then
            export ANSIBLE_STDOUT_CALLBACK=debug
        fi
        if [ "${LSR_CONTAINER_PROFILE:-true}" = true ]; then
            export ANSIBLE_CALLBACKS_ENABLED=profile_tasks
            export ANSIBLE_CALLBACK_WHITELIST=profile_tasks
        fi
        export ANSIBLE_CALLBACK_PLUGINS="$callback_plugin_dir"
    fi
    if [ -z "${ANSIBLE_CONNECTION_PLUGINS:-}" ] || [ ! -f "$ANSIBLE_CONNECTION_PLUGINS/podman.py" ]; then
        local connection_plugin_dir
        connection_plugin_dir="${ANSIBLE_CONNECTION_PLUGINS:-$TOX_WORK_DIR/connection_plugins}"
        local podman_py
        podman_py="$connection_plugin_dir/podman.py"
        if [ ! -f "$podman_py" ]; then
            ansible-galaxy collection install -p "$LSR_TOX_ENV_TMP_DIR" -vv containers.podman
            if [ ! -d "$connection_plugin_dir" ]; then
                mkdir -p "$connection_plugin_dir"
            fi
            mv "$LSR_TOX_ENV_TMP_DIR/ansible_collections/containers/podman/plugins/connection/podman.py" \
                "$podman_py"
            rm -rf "$LSR_TOX_ENV_TMP_DIR/ansible_collections"
        fi
        export ANSIBLE_CONNECTION_PLUGINS="$connection_plugin_dir"
    fi
}

refresh_test_container() {
    local erase_old_snapshot setup_yml
    erase_old_snapshot="${1:-false}"
    setup_yml="${2:-}"
    # see if we need to update our test image - if the test image is older than $CONTAINER_AGE
    # then recreate it
    local age created datepat container_id
    age=$(date +%s --date="$CONTAINER_AGE hours ago")
    created=$(podman image inspect "$CONTAINER_IMAGE" --format='{{.Created}}' 2> /dev/null || :)
    datepat='^([0-9]{4}-[0-9]{2}-[0-9]{2}) ([0-9]{2}:[0-9]{2}:[0-9]{2}[.][0-9]+) ([-+][0-9]+) '
    if [ -z "$created" ]; then
        created=0  # no container
    elif [[ "$created" =~ $datepat ]]; then
        # shellcheck disable=SC2128
        created=$(date --date="$BASH_REMATCH" +%s)
    else
        error invalid date format: "$created"
        return 1
    fi

    # shellcheck disable=SC2086
    if [ "$erase_old_snapshot" = true ] || [ "$created" -lt "$age" ]; then
        local pkgcmd prepkgs initpkgs image_name
        case "$CONTAINER_IMAGE_NAME" in
        *-7) pkgcmd=yum ;
             initpkgs="" ;
             prepkgs="" ;;
        *-8) pkgcmd=dnf ;
             initpkgs="" ;
             prepkgs="" ;;
        *-9) pkgcmd=dnf ;
             initpkgs=systemd ;
             prepkgs="dnf-plugins-core" ;;
        *) pkgcmd=dnf; prepkgs="" ;;
        esac
        for rpm in ${EXTRA_RPMS:-}; do
            initpkgs="$rpm $initpkgs"
        done
        image_name="$CONTAINER_BASE_IMAGE"
        if [ -n "${initpkgs:-}" ]; then
            # some images do not have the entrypoint, so that must be installed
            # first
            container_id=$(podman run -d $CONTAINER_OPTS ${LSR_CONTAINER_OPTS:-} \
                $CONTAINER_MOUNTS "$image_name" sleep 3600)
            if [ -z "$container_id" ]; then
                error Failed to start container
                return 1
            fi
            sleep 1  # ensure container is running
            if ! podman exec -i "$container_id" "$pkgcmd" install -y $initpkgs; then
                podman inspect "$container_id"
                podman rm -f "$container_id"
                return 1
            fi
            if ! podman container commit "$container_id" "$CONTAINER_IMAGE"; then
                podman rm -f "$container_id"
                return 1
            fi
            podman rm -f "$container_id"
            image_name="$CONTAINER_IMAGE"
        fi
        container_id=$(podman run -d $CONTAINER_OPTS ${LSR_CONTAINER_OPTS:-} \
            $CONTAINER_MOUNTS "$image_name" "$CONTAINER_ENTRYPOINT")
        if [ -z "$container_id" ]; then
            error Failed to start container
            return 1
        fi
        sleep 1  # ensure container is running
        inv_file="$(mktemp)"
        echo "sut ansible_host=$container_id ansible_connection=podman" > "$inv_file"
        # shellcheck disable=SC2064
        trap "podman rm -f $container_id; rm -f $inv_file" RETURN
        if [ -n "${prepkgs:-}" ]; then
            if ! podman exec -i "$container_id" "$pkgcmd" install -y $prepkgs; then
                podman inspect "$container_id"
                return 1
            fi
        fi
        if [ -n "${setup_yml:-}" ] && [ -f "${setup_yml}" ] && [ -s "${setup_yml}" ]; then
            if ! ansible-playbook -vv ${CONTAINER_SKIP_TAGS:-} -i "$inv_file" \
                "$setup_yml"; then
                return 1
            fi
        fi
        if ! podman exec -i "$container_id" "$pkgcmd" upgrade -y; then
            podman inspect "$container_id"
            return 1
        fi
        COMMON_PKGS="sudo procps-ng systemd-udev device-mapper openssh-server \
            openssh-clients iproute"
        if ! podman exec -i "$container_id" "$pkgcmd" install -y $COMMON_PKGS; then
            podman inspect "$container_id"
            return 1
        fi
        if [ -f "${CONTAINER_TESTS_PATH}/setup-snapshot.yml" ]; then
            if ! ansible-playbook -vv ${CONTAINER_SKIP_TAGS:-} -i "$inv_file" \
                "${CONTAINER_TESTS_PATH}/setup-snapshot.yml"; then
                return 1
            fi
        fi
        if ! podman container commit "$container_id" "$CONTAINER_IMAGE"; then
            return 1
        fi
    fi
    return 0
}

setup_vault() {
    local test_dir test_basename no_vault_vars vault_pwd_file vault_vars_file
    test_dir="$1"
    test_basename="$2"
    vault_pwd_file="$test_dir/vault_pwd"
    vault_vars_file="$test_dir/vars/vault-variables.yml"
    no_vault_vars="$test_dir/no-vault-variables.txt"
    if [ -f "$vault_pwd_file" ] && [ -f "$vault_vars_file" ]; then
        export ANSIBLE_VAULT_PASSWORD_FILE="$vault_pwd_file"
        vault_args="--extra-vars=@$vault_vars_file"
        if [ -f "$no_vault_vars" ] && grep -q "^${test_basename}$" "$no_vault_vars"; then
            unset ANSIBLE_VAULT_PASSWORD_FILE
            vault_args=""
        fi
    else
        unset ANSIBLE_VAULT_PASSWORD_FILE
        vault_args=""
    fi
}

run_playbooks() {
    # shellcheck disable=SC2086
    local test_pb_base test_dir pb
    declare -a test_pb=()
    test_pb_base="$1"; shift
    for pb in "$@"; do
        pb="$(realpath "$pb")"
        test_pb+=("$pb")
        if [ -z "${test_dir:-}" ]; then
            test_dir="$(dirname "$pb")"
        fi
    done

    container_id=$(podman run -d $CONTAINER_OPTS --name "$test_pb_base" \
        ${LSR_CONTAINER_OPTS:-} $CONTAINER_MOUNTS "$CONTAINER_IMAGE" \
        "$CONTAINER_ENTRYPOINT")

    if [ -z "$container_id" ]; then
        error Failed to start container
        exit 1
    fi

    inv_file="$(mktemp)"
    if [ -z "${LSR_DEBUG:-}" ]; then
        trap "rm -rf $inv_file; podman rm -f $container_id" RETURN EXIT
    fi
    sleep 1  # give the container a chance to start up
    if ! podman exec -i "$container_id" /bin/bash -euxo pipefail -c '
        limit=60
        for ii in $(seq 1 $limit); do
            if systemctl is-active dbus; then
                break
            fi
            sleep 1
        done
        if [ $ii = $limit ]; then
            systemctl status dbus
            exit 1
        fi
        sysctl -w net.ipv6.conf.all.disable_ipv6=0
        systemctl unmask systemd-udevd
        if ! systemctl start systemd-udevd; then
            systemctl status systemd-udevd
            exit 1
        fi
        for ii in $(seq 1 $limit); do
            if systemctl is-active systemd-udevd; then
                break
            fi
            sleep 1
        done
        if [ $ii = $limit ]; then
            systemctl status systemd-udevd
            exit 1
        fi
    '; then
        podman inspect "$container_id"
        return 1
    fi

    echo "sut ansible_host=$container_id ansible_connection=podman" > "$inv_file"
    setup_vault "$test_dir" "${test_pb_base}.yml"
    # shellcheck disable=SC2086
    pushd "$test_dir" > /dev/null
    if [ "$PARALLEL" -gt 0 ]; then
        for pb in ${test_pb[@]}; do
            ansible-playbook -vv ${CONTAINER_SKIP_TAGS:-} ${EXTRA_SKIP_TAGS:-} \
                -i "$inv_file" ${vault_args:-} \
                -e ansible_playbook_filepath="$(type -p ansible-playbook)" "$pb"
        done
    else
        ansible-playbook -vv ${CONTAINER_SKIP_TAGS:-} ${EXTRA_SKIP_TAGS:-} \
            -i "$inv_file" ${vault_args:-} \
            -e ansible_playbook_filepath="$(type -p ansible-playbook)" \
            "${test_pb[@]}"
    fi
    popd > /dev/null
}

# grr - ubuntu 20.04 bash wait does not support -p pid :-(
# also - you cannot call this function in a subshell or it
# defeats the purpose of finding child jobs
# PID is a global variable
lsr_wait() {
    local rc found
    while true; do
        rc=0
        wait -nf || rc=$?
        # now, figure out which pid just exited, if any
        # it might not be one of our playbook jobs that exited
        found=0
        for PID in "${!cur_jobs[@]}"; do
            test -d "/proc/$PID" || { found=1; break; }
        done
        if [ "$found" = 0 ]; then
            sleep 1
        else
            break
        fi
    done
    return "$rc"
}

# PID is a global variable
wait_for_results() {
    local rc test_pb_base
    rc=0
    info waiting for results - pids "${!cur_jobs[*]}" tests "${cur_jobs[*]}"
    for mypid in ${!cur_jobs[*]}; do
        test -d "/proc/$mypid" || echo "$mypid" is not running
    done
    # wait -p pid -n || rc=$?
    lsr_wait || rc=$?
    test_pb_base="${cur_jobs[$PID]}"
    results["$test_pb_base"]="$rc"
    unset cur_jobs["$PID"]
    if [ "$rc" = 0 ]; then
        info Test "$test_pb_base" SUCCESS
    else
        error Test "$test_pb_base" FAILED
    fi
    rc=0
    podman wait "$test_pb_base" > /dev/null 2>&1 || rc=$?
    # 125 is no such container - ok
    if [ "$rc" != 0 ] && [ "$rc" != 125 ]; then
        error container "$test_pb_base" in invalid wait state: "$rc"
    fi
}

ERASE_OLD_SNAPSHOT=false
PARALLEL=0
FAIL_FAST=true
EXTRA_RPMS=()
EXTRA_SKIP_TAGS=""
while [ -n "${1:-}" ]; do
    key="$1"
    case "$key" in
        --image-name)
            shift
            CONTAINER_IMAGE_NAME="$1" ;;
        --config)
            shift
            CONTAINER_CONFIG="$1" ;;
        --erase-old-snapshot)
            ERASE_OLD_SNAPSHOT=true ;;
        --parallel)
            shift
            PARALLEL="$1" ;;
        --fail-fast)
            shift
            FAIL_FAST="$1" ;;
        --log-dir)
            shift
            LOG_DIR="$1" ;;
        --extra-rpm)
            shift
            EXTRA_RPMS+=("$1") ;;
        --extra-skip-tag)
            shift
            EXTRA_SKIP_TAGS="--skip-tags $1 $EXTRA_SKIP_TAGS" ;;
        --*) # unknown option
            echo "Unknown option $1"
            exit 1 ;;
        *) # ansible arg or playbook
            break ;;
    esac
    shift
done

CONTAINER_BASE_IMAGE=$(jq -r '.images[] | select(.name == "'"$CONTAINER_IMAGE_NAME"'") | .container' "$CONTAINER_CONFIG")
if [ "${CONTAINER_BASE_IMAGE:-null}" = null ] ; then
    error container named "$CONTAINER_IMAGE_NAME" not found in "$CONTAINER_CONFIG"
    exit 1
fi
CONTAINER_IMAGE=${CONTAINER_IMAGE:-"lsr-test-$CONTAINER_IMAGE_NAME:latest"}
setup_json=$(mktemp --suffix _setup.json)
setup_yml=$(mktemp --suffix _setup.yml)
jq -r '.images[] | select(.name == "'"$CONTAINER_IMAGE_NAME"'") | .setup' "$CONTAINER_CONFIG" > "$setup_json"
python -c '
import json, yaml, sys
val = json.load(open(sys.argv[1]))
if not val:
  sys.exit(0)
yaml.safe_dump(val, open(sys.argv[2], "w"))
' "$setup_json" "$setup_yml"
rm -f "$setup_json"
if [ -z "${CONTAINER_ENTRYPOINT:-}" ]; then
    case "$CONTAINER_IMAGE_NAME" in
    *-6) CONTAINER_ENTRYPOINT=/sbin/init ;;
    *) CONTAINER_ENTRYPOINT=/usr/sbin/init ;;
    esac
fi

echo ::group::install collection requirements
install_requirements
echo ::endgroup::
echo ::group::install and configure plugins used by tests
setup_plugins
echo ::endgroup::
echo ::group::setup and prepare test container
if ! refresh_test_container "$ERASE_OLD_SNAPSHOT" "$setup_yml"; then
    rm -f "$setup_yml"
    exit 1
fi
echo ::endgroup::
rm -f "$setup_yml"

declare -A cur_jobs=()
declare -A log_files=()
declare -A results=()
declare -A test_pb=()
if [ "$PARALLEL" -gt 1 ]; then
    while [ -n "${1:-}" ]; do
        if [ "${#cur_jobs[*]}" -lt "$PARALLEL" ]; then
            orig_test_pb="$1"; shift
            test_pb="$(realpath "$orig_test_pb")"
            test_pb_base="$(basename "$test_pb" .yml)"
            log_dir="${LOG_DIR:-$(dirname "$test_pb")}"
            log_file="${test_pb_base}.log"
            if [ ! -d "$log_dir" ]; then
                mkdir -p "$log_dir"
            fi
            run_playbooks "$test_pb_base" "$test_pb" > "$log_dir/$log_file" 2>&1 &
            cur_jobs["$!"]="$test_pb_base"
            log_files["$test_pb_base"]="$log_dir/$log_file"
            test_pb["$test_pb_base"]="$orig_test_pb"
            info Starting test "$test_pb_base"
        else
            wait_for_results
        fi
    done
    info All tests executed, waiting for results "${cur_jobs[*]}"
    while [ "${#cur_jobs[*]}" -gt 0 ]; do
        wait_for_results
    done
else
    test_pb_base="$(basename "$1" .yml)"
    run_playbooks "$test_pb_base" "$@"
fi

exit_code=0
for test_pb_base in "${!results[@]}"; do
    rc="${results[$test_pb_base]}"
    log="${log_files[$test_pb_base]}"
    orig_test_pb="${test_pb[$test_pb_base]}"
    if [ "$rc" != 0 ]; then
        exit_code="$rc"
        error "file=${orig_test_pb}::Test" "$test_pb_base FAILED"
    else
        info "file=${orig_test_pb}::Test" "$test_pb_base PASSED"
    fi
done
if [ "$PARALLEL" -gt 1 ]; then
    tar cfz logs.tar.gz "${log_files[@]}"
fi

exit "$exit_code"
