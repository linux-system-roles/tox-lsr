#!/bin/bash

set -euxo pipefail

CONTAINER_OPTS="--privileged --systemd=true --hostname ${CONTAINER_HOSTNAME:-sut}"
CONTAINER_MOUNTS="-v /sys/fs/cgroup:/sys/fs/cgroup"
#CONTAINER_ENTRYPOINT="/usr/sbin/init"
#CONTAINER_IMAGE_NAME=${CONTAINER_IMAGE_NAME:-centos-8}
#CONTAINER_BASE_IMAGE=${CONTAINER_BASE_IMAGE:-quay.io/centos/centos:stream8}
#CONTAINER_IMAGE=${CONTAINER_IMAGE:-lsr-test-$CONTAINER_PLATFORM:latest}
CONTAINER_AGE=${CONTAINER_AGE:-24}  # hours
CONTAINER_TESTS_PATH=${CONTAINER_TESTS_PATH:-"$TOXINIDIR/tests"}
CONTAINER_SKIP_TAGS=${CONTAINER_SKIP_TAGS:---skip-tags tests::no_container}
CONFIG=$HOME/.config/linux-system-roles.json

COLLECTION_BASE_PATH=${COLLECTION_BASE_PATH:-$TOX_WORK_DIR}

install_requirements() {
    if [ -f meta/requirements.yml ]; then
        ansible-galaxy collection install -p "$COLLECTION_BASE_PATH" -vv -r meta/requirements.yml
        export ANSIBLE_COLLECTIONS_PATHS="${ANSIBLE_COLLECTIONS_PATHS:-$COLLECTION_BASE_PATH}"
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
        echo ERROR: invalid date format: "$created"
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
        for rpm in $EXTRA_RPMS; do
            initpkgs="$rpm $initpkgs"
        done
        image_name="$CONTAINER_BASE_IMAGE"
        if [ -n "${initpkgs:-}" ]; then
            # some images do not have the entrypoint, so that must be installed
            # first
            container_id=$(podman run -d $CONTAINER_OPTS ${LSR_CONTAINER_OPTS:-} \
                $CONTAINER_MOUNTS "$image_name" sleep 3600)
            if [ -z "$container_id" ]; then
                echo ERROR: Failed to start container
                return 1
            fi
            if ! podman exec -i "$container_id" "$pkgcmd" install -y $initpkgs; then
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
            echo ERROR: Failed to start container
            return 1
        fi
        # shellcheck disable=SC2064
        trap "podman rm -f $container_id" RETURN
        if [ -n "${prepkgs:-}" ]; then
            if ! podman exec -i "$container_id" "$pkgcmd" install -y $prepkgs; then
                return 1
            fi
        fi
        if [ -n "${setup_yml:-}" ] && [ -f "${setup_yml}" ]; then
            if ! ansible-playbook -vv ${CONTAINER_SKIP_TAGS:-} -c podman -i "$container_id", \
                "$setup_yml"; then
                return 1
            fi
        fi
        if ! podman exec -i "$container_id" "$pkgcmd" upgrade -y; then
            return 1
        fi
        COMMON_PKGS="sudo procps-ng systemd-udev device-mapper openssh-server \
            openssh-clients"
        if ! podman exec -i "$container_id" "$pkgcmd" install -y $COMMON_PKGS; then
            return 1
        fi
        if [ -f "${CONTAINER_TESTS_PATH}/setup-snapshot.yml" ]; then
            if ! ansible-playbook -vv ${CONTAINER_SKIP_TAGS:-} -c podman -i "$container_id", \
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

ERASE_OLD_SNAPSHOT=false
EXCLUDES=()
EXTRA_RPMS=()
while [ -n "${1:-}" ]; do
    key="$1"
    case "$key" in
        --image-name)
            shift
            CONTAINER_IMAGE_NAME="$1" ;;
        --config)
            shift
            CONFIG="$1" ;;
        --erase-old-snapshot)
            ERASE_OLD_SNAPSHOT=true ;;
        --containers)
            shift
            CONTAINER_COUNT="$1" ;;
        --exclude)
            shift
            EXCLUDES+=("$1") ;;
        --extra-rpm)
            shift
            EXTRA_RPMS+=("$1") ;;
        --*) # unknown option
            echo "Unknown option $1"
            exit 1 ;;
        *) # ansible arg or playbook
            break ;;
    esac
    shift
done

CONTAINER_BASE_IMAGE=$(jq -r '.images[] | select(.name == "'"$CONTAINER_IMAGE_NAME"'") | .container' "$CONFIG")
if [ "${CONTAINER_BASE_IMAGE:-null}" = null ] ; then
    echo ERROR: container named "$CONTAINER_IMAGE_NAME" not found in "$CONFIG"
    exit 1
fi
CONTAINER_IMAGE=${CONTAINER_IMAGE:-"lsr-test-$CONTAINER_IMAGE_NAME:latest"}
setup_json=$(mktemp --suffix _setup.json)
setup_yml=$(mktemp --suffix _setup.yml)
jq -r '.images[] | select(.name == "'"$CONTAINER_IMAGE_NAME"'") | .setup' "$CONFIG" > "$setup_json"
python -c '
import json, yaml, sys
val = json.load(open(sys.argv[1]))
yaml.safe_dump(val, open(sys.argv[2], "w"))
' "$setup_json" "$setup_yml"
rm -f "$setup_json"
if [ -z "${CONTAINER_ENTRYPOINT:-}" ]; then
    case "$CONTAINER_IMAGE_NAME" in
    *-6) CONTAINER_ENTRYPOINT=/sbin/init ;;
    *) CONTAINER_ENTRYPOINT=/usr/sbin/init ;;
    esac
fi

install_requirements
setup_plugins

clean_up() {
    podman rm -f "$CONTAINER_ID" || true
    rm -f "$setup_yml"
}

export TEST_ARTIFACTS="${TEST_ARTIFACTS:-artifacts}"

run_one_container() {
    if ! refresh_test_container "$ERASE_OLD_SNAPSHOT" "$setup_yml"; then
        rm -f "$setup_yml"
        exit 1
    fi

    # shellcheck disable=SC2086
    CONTAINER_ID=$(podman run -d $CONTAINER_OPTS ${LSR_CONTAINER_OPTS:-} \
        $CONTAINER_MOUNTS "$CONTAINER_IMAGE" "$CONTAINER_ENTRYPOINT")

    if [ -z "$CONTAINER_ID" ]; then
        echo ERROR: Failed to start container
        rm -f "$setup_yml"
        exit 1
    fi

    if [ -z "${DEBUG:-}" ]; then
        trap clean_up EXIT
    fi

    podman exec -i "$CONTAINER_ID" /bin/bash -euxo pipefail -c '
        limit=30
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
        systemctl start systemd-udevd
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
    '

    # shellcheck disable=SC2086
    ansible-playbook -vv ${CONTAINER_SKIP_TAGS:-} -c podman -i "$CONTAINER_ID", "$@"
}

is_included() {
    for excl in ${EXCLUDES[@]}; do
        if [[ $1 == *$excl ]]; then
            return 1
        fi
    done
    return 0
}

# Drop to be excluded tests from the test list
playbooks=()
for test in $@; do
    if is_included "$test"; then
        playbooks+=("$test")
    fi
done

CONTAINER_COUNT=${CONTAINER_COUNT:-1}
if [ $CONTAINER_COUNT -eq 1 ]; then
    run_one_container ${playbooks[@]} &
elif [ $CONTAINER_COUNT -lt 1 ]; then
    echo "ERROR: Container count $CONTAINER_COUNT is not positive"
    exit 1
else
    # Divide the test list and run each list on one container
    pbcount=${#playbooks[@]}
    quotient=$(($pbcount / $CONTAINER_COUNT))
    begin=0
    width=$(($quotient + 1))
    remainder=$(($pbcount % $CONTAINER_COUNT))
    left=$pbcount
    while [ $remainder -gt 0 ]; do
        run_one_container ${playbooks[@]:$begin:$width} &
        begin=$(($begin + $width))
        left=$(($left - $width))
        remainder=$(($remainder - 1))
    done

    width=$quotient
    while [ $left -gt 0 ]; do
        run_one_container ${playbooks[@]:$begin:$width} &
        begin=$(($begin + $width))
        left=$(($left - $width))
    done
fi
