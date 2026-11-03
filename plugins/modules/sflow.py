#!/usr/bin/python
#
# GNU General Public License v3.0+ (see https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import (absolute_import, division, print_function)
__metaclass__ = type


DOCUMENTATION = r'''
---
module: sflow
short_description: Configure global sFlow settings on SONiC
version_added: "0.4.0"
description:
  - Manage the global sFlow state (the C(SFLOW|global) entry in CONFIG_DB), that is
    the admin state, the agent interface, the counter polling interval and the
    default sampling direction.
  - Only the options that are given are written; the other fields of the entry
    are left as they are.
  - Collectors are managed with M(community.sonic.sflow_collector) and
    per-interface sessions with M(community.sonic.sflow_session).
  - The C(sflow) container must be enabled in the C(FEATURE) table for the
    configuration to take effect.
extends_documentation_fragment:
  - community.sonic.attributes
attributes:
  check_mode:
    support: full
  diff_mode:
    support: full
options:
  enabled:
    description:
      - Whether sFlow sampling is enabled.
      - V(true) sets C(admin_state=up) and V(false) sets C(admin_state=down).
    type: bool
  agent_id:
    description:
      - The interface whose address is used as the sFlow agent address, for
        example V(eth0) or a loopback interface.
      - Physical ports may be given by alias and are stored under their
        C(EthernetN) name.
      - An empty string removes the configured agent interface, in which case
        SONiC picks the agent address itself.
    type: str
  polling_interval:
    description:
      - Counter polling interval in seconds.
      - SONiC accepts V(0) (polling disabled) or a value between V(5) and V(300).
    type: int
  sample_direction:
    description: Default sampling direction for interfaces without their own setting.
    type: str
    choices: [rx, tx, both]
  state:
    description:
      - V(present) applies the given options.
      - V(absent) removes the C(SFLOW|global) entry altogether, which disables
        sFlow and forgets the agent interface and polling interval.
    type: str
    choices: [present, absent]
    default: present

author:
  - Christian Svensson (@bluecmd)
'''

EXAMPLES = r'''
- name: Enable sFlow with eth0 as the agent interface
  community.sonic.sflow:
    enabled: true
    agent_id: eth0
    sample_direction: rx

- name: Poll counters every 20 seconds
  community.sonic.sflow:
    polling_interval: 20

- name: Disable sFlow but keep the other settings
  community.sonic.sflow:
    enabled: false

- name: Remove the global sFlow configuration
  community.sonic.sflow:
    state: absent
'''

RETURN = r'''
agent_id:
  description: The agent interface name as stored in CONFIG_DB, when O(agent_id) was given.
  type: str
  returned: when O(agent_id) is set
  sample: Ethernet0
'''

import re

from ansible.module_utils.basic import AnsibleModule
from ansible_collections.community.sonic.plugins.module_utils.config_db import (
    ConfigDB, ConfigDBError, UnknownInterfaceError, bool_to_up_down, resolve_interface_name)

TABLE = 'SFLOW'
KEY = 'global'

_MGMT_PORT_RE = re.compile(r'^eth\d+$')


def resolve_agent_interface(port_table, mgmt_port_table, name):
    """Return the CONFIG_DB name of the sFlow agent interface.

    Physical ports may be given by alias. PortChannel, Vlan and Loopback names
    pass through and so do management ports (``eth0``), which are not in the
    ``PORT`` table.
    """
    try:
        return resolve_interface_name(port_table, name)
    except UnknownInterfaceError:
        if name in mgmt_port_table or _MGMT_PORT_RE.match(str(name)):
            return name
        raise UnknownInterfaceError('could not find interface "%s" to use as the sFlow agent' % name)


def build_sflow_entry(state, enabled=None, agent_id=None, polling_interval=None, sample_direction=None):
    """Return the fields to merge into ``SFLOW|global``, or ``None`` for ``state=absent``.

    ``agent_id`` is expected to be resolved already; an empty string maps to
    ``None`` which removes the field.
    """
    if state == 'absent':
        return None
    desired = {}
    if enabled is not None:
        desired['admin_state'] = bool_to_up_down(enabled)
    if agent_id is not None:
        desired['agent_id'] = agent_id or None
    if polling_interval is not None:
        desired['polling_interval'] = polling_interval
    if sample_direction is not None:
        desired['sample_direction'] = sample_direction
    return desired


def run_module():
    module_args = dict(
        enabled=dict(type='bool'),
        agent_id=dict(type='str'),
        polling_interval=dict(type='int'),
        sample_direction=dict(type='str', choices=['rx', 'tx', 'both']),
        state=dict(type='str', default='present', choices=['present', 'absent']),
    )

    module = AnsibleModule(
        argument_spec=module_args,
        supports_check_mode=True,
        required_if=(('state', 'present', ('enabled', 'agent_id', 'polling_interval', 'sample_direction'), True),),
    )
    params = module.params

    polling_interval = params['polling_interval']
    if polling_interval is not None and not (polling_interval == 0 or 5 <= polling_interval <= 300):
        module.fail_json(msg='polling_interval must be 0 or between 5 and 300, got %d' % polling_interval)

    db = ConfigDB(module).connect()

    agent_id = params['agent_id']
    extra = {}
    try:
        if agent_id:
            agent_id = resolve_agent_interface(db.port_table(), db.get_table('MGMT_PORT'), agent_id)
            extra['agent_id'] = agent_id
        desired = build_sflow_entry(params['state'], params['enabled'], agent_id,
                                    polling_interval, params['sample_direction'])
        change = db.ensure_entry(TABLE, KEY, desired, exclusive=False)
    except ConfigDBError as e:
        module.fail_json(msg=str(e))

    module.exit_json(**change.result(**extra))


def main():
    run_module()


if __name__ == '__main__':
    main()
