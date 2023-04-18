#!/usr/bin/python
# TODO: describe
#
# GNU General Public License v3.0+ (see https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import (absolute_import, division, print_function)
__metaclass__ = type


DOCUMENTATION = r'''
---
module: sonic_interface_port
short_description: Configure a SONiC interface port
version_added: "0.0.1"
description: Manage all settings related to interface ports in SONiC
options:
    interface:
        description: The interface name to operate on. Alias naming is supported.
        required: true
        type: str
    description:
        description: Update the interface description to this string
        required: false
        type: str
author:
    - Christian Svensson (@bluecmd)
'''

EXAMPLES = r'''
# Set the interface description of a port
- name: Set port description
  community.sonic.sonic_interface_port:
    interface: qsfp1
    description: This is the uplink
'''

RETURN = r'''
interface:
    description: The resolved interface name
    type: str
    returned: always
'''

import copy
import traceback

from ansible.module_utils.basic import AnsibleModule, missing_required_lib

try:
    from swsscommon import swsscommon
except ImportError:
    HAS_SWSSCOMMON_LIBRARY = False
    SWSSCOMMON_IMPORT_ERROR = traceback.format_exc()
else:
    HAS_SWSSCOMMON_LIBRARY = True
    SWSSCOMMON_IMPORT_ERROR = None


def run_module():
    module_args = dict(
        interface=dict(type='str', required=True),
        description=dict(type='str', required=False),
    )

    changed = False
    module = AnsibleModule(
        argument_spec=module_args,
        supports_check_mode=True
    )

    if not HAS_SWSSCOMMON_LIBRARY:
        module.fail_json(
            msg=missing_required_lib('swsscommon'),
            exception=SWSSCOMMON_IMPORT_ERROR)

    config_db = swsscommon.ConfigDBConnector()
    config_db.connect()
    port_table = config_db.get_table('PORT')
    port_alias_table = {v['alias']: k for k, v in port_table.items() if 'alias' in v}

    ifname = port_alias_table.get(module.params['interface'], module.params['interface'])
    if ifname not in port_table:
        module.fail_json(msg=f'could not find interface "{ifname}"')

    current_state = port_table[ifname]
    new_state = copy.copy(current_state)

    if 'description' in current_state:
        if module.params['description'] == '' or module.params['description'] is None:
            del new_state['description']
            changed = True
    if module.params['description'] and (
            module.params['description'] != current_state.get('description', '')):
        new_state['description'] = module.params['description']
        changed = True

    if module.check_mode:
        module.exit_json(changed=changed, interface=ifname)

    if not changed:
        module.exit_json(changed=changed, interface=ifname)

    if 'description' in current_state and 'description' not in new_state:
        # Specifically for description, if it has been removed we need to clean
        # it up from APPL_DB / PORT_TABLE since that is not done automatically
        # as of this writing (2023-04-15).
        # The cleanest way to do this is to set the description to '' before
        # deleting it, which triggers the APPL_DB to refresh.
        config_db.mod_entry('PORT', ifname, {'description': ''})

    config_db.set_entry('PORT', ifname, new_state)

    module.exit_json(changed=changed, interface=ifname)


def main():
    run_module()


if __name__ == '__main__':
    main()
