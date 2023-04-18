#!/bin/bash

set -euo pipefail

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
script -e -c "ansible-test network-integration ${*}" /dev/null
