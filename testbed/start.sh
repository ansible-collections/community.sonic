#!/bin/bash

set -euo pipefail

echo ' - Doing static analysis while virtual SONiC starts'

ansible-galaxy collection install $PWD

yamllint -s .
ansible-lint .
ansible-test sanity \
  --python $(python -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")') \
  plugins/ \
  tests/integration/

echo ' - Building documentation'

mkdir -p tests/output/docs
antsibull-docs sphinx-init --use-current --fail-on-error --dest-dir tests/output/docs community.sonic
(cd tests/output/docs; pip3 install -r requirements.txt > /dev/null; ./build.sh)

echo ' - Waiting for virtual SONiC to start'
until [ -S /tmp/sonic-vs.sock ]
do
  sleep 1
done

# TODO: We can do this much faster, SONiC has fixed timers for some services to start
until timeout 2s sshpass -p YourPaSsWoRd ssh admin@sonic-vs systemctl is-active pmon.service -q
do
  sleep 1
done

sleep 60
echo ' - Virtual SONiC started'

export ANSIBLE_CONFIG=$PWD/testbed/ansible.cfg
script -e -c "ansible-test network-integration ${@}" /dev/null
