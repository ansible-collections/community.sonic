#!/usr/bin/python
#
# GNU General Public License v3.0+ (see https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import (absolute_import, division, print_function)
__metaclass__ = type


DOCUMENTATION = r'''
---
module: sflow_session
short_description: Configure per-interface sFlow sessions on SONiC
version_added: "0.4.0"
description:
  - Manage per-interface sFlow sampling (the C(SFLOW_SESSION) table in
    CONFIG_DB), the admin state, sampling rate and direction of a port, or the
    defaults for all ports through the special C(all) entry.
  - Only the options that are given are written; the other fields of the entry
    are left as they are. Use O(state=absent) to remove the entry and fall back
    to the global defaults.
  - Global sFlow settings are managed with M(community.sonic.sflow) and
    collectors with M(community.sonic.sflow_collector).
extends_documentation_fragment:
  - community.sonic.attributes
attributes:
  check_mode:
    support: full
  diff_mode:
    support: full
options:
  interface:
    description:
      - The physical port to configure. Alias naming is supported.
      - V(all) configures the defaults for every port.
    type: str
    required: true
  enabled:
    description:
      - Whether sampling is enabled on the interface.
      - V(true) sets C(admin_state=up) and V(false) sets C(admin_state=down).
      - Disabling a port excludes it from sampling while sFlow stays enabled
        globally.
    type: bool
  sample_rate:
    description:
      - Sample one packet out of this many.
      - SONiC accepts values between V(256) and V(8388608).
    type: int
  sample_direction:
    description: Sampling direction for the interface.
    type: str
    choices: [rx, tx, both]
  state:
    description:
      - V(present) applies the given options.
      - V(absent) removes the session entry so the interface follows the
        global settings again.
    type: str
    choices: [present, absent]
    default: present

author:
  - Christian Svensson (@bluecmd)
'''

EXAMPLES = r'''
- name: Do not sample the inter-switch links
  community.sonic.sflow_session:
    interface: "{{ item }}"
    enabled: false
  loop: [QSFP1, QSFP21, QSFP31]

- name: Sample one packet in 4096 on an edge port, ingress only
  community.sonic.sflow_session:
    interface: Ethernet8
    enabled: true
    sample_rate: 4096
    sample_direction: rx

- name: Set the default sample rate for all ports
  community.sonic.sflow_session:
    interface: all
    sample_rate: 8192

- name: Let a port follow the global settings again
  community.sonic.sflow_session:
    interface: Ethernet8
    state: absent
'''

RETURN = r'''
interface:
  description: The port name as stored in CONFIG_DB (C(EthernetN) or C(all)).
  type: str
  returned: always
  sample: Ethernet0
'''

from ansible.module_utils.basic import AnsibleModule
from ansible_collections.community.sonic.plugins.module_utils.config_db import ConfigDB, ConfigDBError, bool_to_up_down

TABLE = 'SFLOW_SESSION'
ALL_PORTS = 'all'
MIN_SAMPLE_RATE = 256
MAX_SAMPLE_RATE = 8388608


def build_session_entry(state, enabled=None, sample_rate=None, sample_direction=None):
    """Return the fields to merge into the ``SFLOW_SESSION`` entry, or ``None`` for ``state=absent``."""
    if state == 'absent':
        return None
    desired = {}
    if enabled is not None:
        desired['admin_state'] = bool_to_up_down(enabled)
    if sample_rate is not None:
        desired['sample_rate'] = sample_rate
    if sample_direction is not None:
        desired['sample_direction'] = sample_direction
    return desired


def run_module():
    module_args = dict(
        interface=dict(type='str', required=True),
        enabled=dict(type='bool'),
        sample_rate=dict(type='int'),
        sample_direction=dict(type='str', choices=['rx', 'tx', 'both']),
        state=dict(type='str', default='present', choices=['present', 'absent']),
    )

    module = AnsibleModule(
        argument_spec=module_args,
        supports_check_mode=True,
        required_if=(('state', 'present', ('enabled', 'sample_rate', 'sample_direction'), True),),
    )
    params = module.params

    sample_rate = params['sample_rate']
    if sample_rate is not None and not (MIN_SAMPLE_RATE <= sample_rate <= MAX_SAMPLE_RATE):
        module.fail_json(msg='sample_rate must be between %d and %d, got %d' % (MIN_SAMPLE_RATE, MAX_SAMPLE_RATE, sample_rate))

    db = ConfigDB(module).connect()

    try:
        interface = params['interface']
        if interface != ALL_PORTS:
            interface = db.resolve_port(interface)
        desired = build_session_entry(params['state'], params['enabled'], sample_rate, params['sample_direction'])
        change = db.ensure_entry(TABLE, interface, desired, exclusive=False)
    except ConfigDBError as e:
        module.fail_json(msg=str(e))

    module.exit_json(**change.result(interface=interface))


def main():
    run_module()


if __name__ == '__main__':
    main()
