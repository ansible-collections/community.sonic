#!/usr/bin/env bash

set -euo pipefail

echo ' - Waiting for virtual SONiC to start'
# Bound startup waiting so failed boots produce a useful log instead of
# occupying the runner until the pipeline-wide timeout.
deadline=$((SECONDS + ${SONIC_BOOT_TIMEOUT:-600}))
# TODO: We can do this much faster, SONiC has fixed timers for some services to start
until timeout 2s sshpass -p YourPaSsWoRd ssh admin@sonic-vs systemctl is-active pmon.service -q
do
  if (( SECONDS >= deadline )); then
    echo 'Timed out waiting for virtual SONiC' >&2
    tail -n 100 /tmp/qemu.log >&2 || true
    exit 1
  fi
  sleep 1
done

sleep 60
echo ' - Virtual SONiC started'

export ANSIBLE_CONFIG="$PWD/testbed/ansible.cfg"
script -e -c "ansible-test network-integration --continue-on-error ${*}" /dev/null
