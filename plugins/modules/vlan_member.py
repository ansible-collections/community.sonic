#!/usr/bin/python
#
# GNU General Public License v3.0+ (see https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import (absolute_import, division, print_function)
__metaclass__ = type


DOCUMENTATION = r'''
---
module: vlan_member
short_description: Configure SONiC VLAN port memberships
version_added: "0.2.0"
description: Manage VLAN port memberships in SONiC
extends_documentation_fragment:
  - community.sonic.attributes
attributes:
  check_mode:
    support: full
  diff_mode:
    support: full
options:
    vlanid:
        description: The VLAN to manage the interface membership for
        required: true
        type: int
    state:
        description: Whether the interface should be attached to the VLAN or not
        default: present
        type: str
        choices: [present, absent]
    interface:
        description:
          - The interface to attach to the VLAN, a port by name (C(Ethernet0)) or alias (C(QSFP1)),
            or a PortChannel (C(PortChannel3)).
        required: true
        type: str
    tagged:
        description: Whether the VLAN should be tagged for the interface or not, required when I(state=present)
        type: bool

author:
    - Erik Larsson (@whooo)
'''

EXAMPLES = r'''
# Add an interface to VLAN
- name: Add interface to VLAN
  community.sonic.vlan_member:
    vlanid: 3600
    interface: Ethernet90
    tagged: true

# Remove an interface from a VLAN
- name: Remove interface from VLAN
  community.sonic.vlan_member:
    vlanid: 3600
    state: absent
    interface: Ethernet90

# Add an untagged interface
- name: VLAN membership untagged
  community.sonic.vlan_member:
    vlanid: 3600
    interface: Ethernet90
    tagged: false

# Add a PortChannel
- name: PortChannel VLAN membership
  community.sonic.vlan_member:
    vlanid: 3600
    interface: PortChannel3
    tagged: true
'''

RETURN = r'''
interface:
    description: The canonical name of the member interface, resolved from an alias when one was given.
    type: str
    returned: always
    sample: Ethernet90
'''

from ansible.module_utils.basic import AnsibleModule
from ansible_collections.community.sonic.plugins.module_utils.config_db import (
    ConfigDB, ConfigDBError, UnsupportedInterfaceError, interface_kind, join_key)

#: Interface kinds that can be VLAN members.
MEMBER_KINDS = ('Ethernet', 'PortChannel')


def build_vlan_member_entry(vlanid, interface, state, tagged):
    key = join_key(f'Vlan{vlanid}', interface)
    # No reason to build the entry if state is absent
    if state == 'absent':
        return key, None

    val = {
        'tagging_mode': 'tagged' if tagged else 'untagged',
    }
    return key, val


def run_module():
    module_args = dict(
        vlanid=dict(type='int', required=True),
        state=dict(type='str', default='present', choices=['present', 'absent'], required=False),
        interface=dict(type='str', required=True),
        tagged=dict(type='bool', required=False),
    )

    module = AnsibleModule(
        argument_spec=module_args,
        supports_check_mode=True,
        # Don't require the tagged option if we want to remove the membership
        required_if=(('state', 'present', ('tagged',), True),),
    )

    config_db = ConfigDB(module).connect()

    params = dict(module.params)
    try:
        params['interface'] = config_db.resolve_interface(params['interface'])
        if interface_kind(params['interface']) not in MEMBER_KINDS:
            raise UnsupportedInterfaceError(
                'interface "%s" cannot be a VLAN member; expected a port or PortChannel' % params['interface'])
        key, val = build_vlan_member_entry(**params)
        change = config_db.ensure_entry('VLAN_MEMBER', key, val, exclusive=True)
    except ConfigDBError as e:
        module.fail_json(msg=str(e))

    module.exit_json(**change.result(interface=params['interface']))


def main():
    run_module()


if __name__ == '__main__':
    main()
