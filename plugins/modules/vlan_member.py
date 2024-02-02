#!/usr/bin/python
#
# GNU General Public License v3.0+ (see https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import (absolute_import, division, print_function)
__metaclass__ = type


DOCUMENTATION = r'''
---
module: vlan_member
short_description: Configure a SONiC VLAN port memberships
version_added: "0.2.0"
description: Manage VLAN port memberships in SONiC
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
        description: The interface to attach to the VLAN
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
'''

from ansible.module_utils.basic import AnsibleModule, missing_required_lib
from ansible_collections.community.sonic.plugins.module_utils.entries import compare_entries
from ansible_collections.community.sonic.plugins.module_utils.imports import get_swsscommon


def build_vlan_member_entry(vlanid, interface, state, tagged):
    key = f'Vlan{vlanid}|{interface}'
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

    swsscommon, swsscommon_traceback = get_swsscommon()
    if swsscommon_traceback:
        module.fail_json(
            msg=missing_required_lib('swsscommon'),
            exception=swsscommon_traceback)

    config_db = swsscommon.ConfigDBConnector()
    config_db.connect()

    key, val = build_vlan_member_entry(**module.params)
    cur_val = config_db.get_entry('VLAN_MEMBER', key)
    changed = compare_entries(val, cur_val)

    if module.check_mode or not changed:
        module.exit_json(changed=changed)

    config_db.set_entry('VLAN_MEMBER', key, val)

    module.exit_json(changed=changed)


def main():
    run_module()


if __name__ == '__main__':
    main()
