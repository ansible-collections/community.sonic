#!/usr/bin/python
#
# GNU General Public License v3.0+ (see https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import (absolute_import, division, print_function)
__metaclass__ = type


DOCUMENTATION = r'''
---
module: sflow_collector
short_description: Configure sFlow collectors on SONiC
version_added: "0.4.0"
description:
  - Manage sFlow collectors (the C(SFLOW_COLLECTOR) table in CONFIG_DB).
  - SONiC supports at most two collectors; adding a third fails.
  - Global sFlow settings are managed with M(community.sonic.sflow) and
    per-interface sessions with M(community.sonic.sflow_session).
extends_documentation_fragment:
  - community.sonic.attributes
attributes:
  check_mode:
    support: full
  diff_mode:
    support: full
options:
  name:
    description: Name of the collector, at most 16 characters.
    type: str
    required: true
  address:
    description:
      - IPv4 or IPv6 address of the collector.
      - Required when O(state=present).
    type: str
  port:
    description: UDP port the collector listens on.
    type: int
    default: 6343
  vrf:
    description:
      - VRF through which the collector is reached.
      - Use V(mgmt) when the collector is only reachable over the management VRF.
    type: str
    choices: [default, mgmt]
    default: default
  state:
    description: Whether the collector should be present or absent.
    type: str
    choices: [present, absent]
    default: present

author:
  - Christian Svensson (@bluecmd)
'''

EXAMPLES = r'''
- name: Export flows to a collector over the management VRF
  community.sonic.sflow_collector:
    name: flow-collector
    address: 2001:db8::18
    port: 6343
    vrf: mgmt

- name: Collector in the default VRF on the default port
  community.sonic.sflow_collector:
    name: backup
    address: 192.0.2.18

- name: Remove a collector
  community.sonic.sflow_collector:
    name: backup
    state: absent
'''

RETURN = r'''
name:
  description: The collector name.
  type: str
  returned: always
  sample: flow-collector
'''

import ipaddress

from ansible.module_utils.basic import AnsibleModule
from ansible_collections.community.sonic.plugins.module_utils.config_db import ConfigDB, ConfigDBError

TABLE = 'SFLOW_COLLECTOR'
MAX_COLLECTORS = 2
MAX_NAME_LENGTH = 16


def build_collector_entry(state, address=None, port=6343, vrf='default'):
    """Return the ``SFLOW_COLLECTOR`` entry for the given options, or ``None`` for ``state=absent``."""
    if state == 'absent':
        return None
    return {
        'collector_ip': address,
        'collector_port': port,
        'collector_vrf': vrf,
    }


def run_module():
    module_args = dict(
        name=dict(type='str', required=True),
        address=dict(type='str'),
        port=dict(type='int', default=6343),
        vrf=dict(type='str', default='default', choices=['default', 'mgmt']),
        state=dict(type='str', default='present', choices=['present', 'absent']),
    )

    module = AnsibleModule(
        argument_spec=module_args,
        supports_check_mode=True,
        required_if=(('state', 'present', ('address',)),),
    )
    params = module.params
    name = params['name']

    if not name or len(name) > MAX_NAME_LENGTH:
        module.fail_json(msg='collector name "%s" must be between 1 and %d characters' % (name, MAX_NAME_LENGTH))
    if not (0 <= params['port'] <= 65535):
        module.fail_json(msg='port must be between 0 and 65535, got %d' % params['port'])
    address = params['address']
    if address is not None:
        try:
            address = str(ipaddress.ip_address(address))
        except ValueError:
            module.fail_json(msg='collector address "%s" is not a valid IP address' % address)

    db = ConfigDB(module).connect()

    try:
        if params['state'] == 'present':
            existing = db.get_keys(TABLE)
            if name not in existing and len(existing) >= MAX_COLLECTORS:
                module.fail_json(msg='only %d sFlow collectors can be configured, found: %s' % (
                    MAX_COLLECTORS, ', '.join(sorted(existing))))
        desired = build_collector_entry(params['state'], address, params['port'], params['vrf'])
        change = db.ensure_entry(TABLE, name, desired, exclusive=True)
    except ConfigDBError as e:
        module.fail_json(msg=str(e))

    module.exit_json(**change.result(name=name))


def main():
    run_module()


if __name__ == '__main__':
    main()
