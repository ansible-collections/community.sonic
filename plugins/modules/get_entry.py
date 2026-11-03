#!/usr/bin/python
#
# GNU General Public License v3.0+ (see https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import (absolute_import, division, print_function)
__metaclass__ = type


DOCUMENTATION = r'''
---
module: get_entry
short_description: Get table/entry from SONiC configuration database
version_added: "0.2.0"
description: Read a table or entry from the SONiC configuration database
extends_documentation_fragment:
  - community.sonic.attributes
attributes:
  check_mode:
    support: full
  diff_mode:
    support: none
options:
    table:
        description: The table to lookup
        required: true
        type: str
    key:
        description: The key to look up in table
        type: str

author:
    - Erik Larsson (@whooo)
'''

EXAMPLES = r'''
# Get table
- name: get vlan table
  community.sonic.get_entry:
    table: VLAN

# Get entry in table
- name: get entry in vlan table
  community.sonic.get_entry:
    table: VLAN
    key: Vlan3600
'''

RETURN = r'''
table:
    description: The database table
    type: str
    returned: always
key:
    description: The entry key
    type: str
    returned: when a key was passed to the module
value:
    description: The database value
    type: dict
    returned: always
'''

from ansible.module_utils.basic import AnsibleModule
from ansible_collections.community.sonic.plugins.module_utils.config_db import ConfigDB


def run_module():
    module_args = dict(
        table=dict(type='str', required=True),
        key=dict(type='str', required=False, no_log=False),
    )

    module = AnsibleModule(
        argument_spec=module_args,
        supports_check_mode=True
    )

    config_db = ConfigDB(module).connect()

    table = module.params.get('table')
    key = module.params.get('key', None)
    if key is None:
        value = config_db.get_table(table)
    else:
        value = config_db.get_entry(table, key)

    rargs = {
        'changed': False,
        'table': table,
        'value': value,
    }
    # If the whole table was requested, don't return the key as it will be None
    if key is not None:
        rargs['key'] = key
    module.exit_json(**rargs)


def main():
    run_module()


if __name__ == '__main__':
    main()
