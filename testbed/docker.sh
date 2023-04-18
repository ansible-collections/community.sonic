#!/bin/bash

set -euo pipefail

(sleep 1; echo) | \
  (ip2unix -r in,port=5555,path=/tmp/sonic-vs.sock \
  qemu-system-x86_64 -snapshot -machine q35 -accel kvm \
    -m 4096 -cpu host -smp 4 -hda /opt/sonic-vs.img -nographic \
    -netdev user,id=sonic0,hostfwd=tcp::5555-:22 \
    -device e1000,netdev=sonic0 2>&1 | ts > /tmp/qemu.log \
    || (echo; echo 'QEMU exited, aborting job'; tail /tmp/qemu.log; kill -9 $$)) &

exec ./testbed/start.sh
