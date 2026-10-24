#!/usr/bin/env bash

set -euo pipefail

if ! getent passwd "$(id -u)" >/dev/null; then
  echo 'The container UID needs a passwd entry for SSH; build with TESTBED_UID/TESTBED_GID matching your user' >&2
  exit 1
fi

(sleep 1; echo) | \
  (qemu-system-x86_64 -snapshot -machine q35 -accel kvm \
    -m "${SONIC_MEMORY_MIB:-8192}" -cpu host -smp 4 -hda /opt/sonic-vs.img -nographic \
    -netdev user,id=sonic0,hostfwd=tcp:127.0.0.1:5555-:22 \
    -device e1000,netdev=sonic0 2>&1 | ts > /tmp/qemu.log \
    || (echo; echo 'QEMU exited, aborting job'; tail /tmp/qemu.log; kill -9 $$)) &

exec ./testbed/start.sh
