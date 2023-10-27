#!/usr/bin/python
#
# GNU General Public License v3.0+ (see https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import (absolute_import, division, print_function)
__metaclass__ = type


DOCUMENTATION = r'''
---
module: interface_ip
short_description: Configure interface IP addresses
version_added: "0.2.0"
description: Configures IP addresses for interfaces
options:
    interface:
        description: The interface to manage IP addresses for
        required: true
        type: str
    state:
        description: Whether the IP addresses should be present or absent
        default: present
        type: str
        choices: [present, absent]
    addresses:
        description: The IP addresses to add or remove from the interface including prefix
        required: true
        type: list
        elements: str

author:
    - Erik Larsson (@whooo)
'''

EXAMPLES = r'''
# Add addresses
- name: Add addresses
  community.sonic.interface_ip:
    interface: Loopback0
    addresses:
      - '10.2.0.2/24'
      - '2f00::2/64'

# Remove address
- name: Remove address
  community.sonic.interface_ip:
    interface: Loopback0
    state: absent
    addresses:
      - '2f00::2/64'

'''

RETURN = r'''
interface:
    description: The interface being managed
    type: str
    returned: always
addresses:
    description: The addresses which has been added or removed
    type: list
    elements: str
    returned: always
'''

# FIXME, return values

import ipaddress
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


def get_interface_table(interface):
    # If the interface name contains a dot it's VLAN subinterface
    if '.' in interface:
        return 'VLAN_SUB_INTERFACE'
    elif interface.startswith('Vlan'):
        return 'VLAN_INTERFACE'
    elif interface.startswith('Ethernet'):
        return 'INTERFACE'
    elif interface.startswith('PortChannel'):
        return 'PORTCHANNEL_INTERFACE'
    elif interface.startswith('Loopback'):
        return 'LOOPBACK_INTERFACE'
    return None


def is_vlan_member(config_db, interface):
    table = config_db.get_table('VLAN_MEMBER')
    for key in table.keys():
        if not isinstance(key, tuple):
            continue
        iface = key[1]  # key is (vlan, interface)
        if iface == interface:
            return True
    return False


def get_current_addresses(config_db, table, interface):
    addresses = set()
    value = config_db.get_table(table)
    for key in value:
        if not isinstance(key, tuple):
            continue
        iface, addr = key
        if iface != interface:
            continue
        pa = ipaddress.ip_interface(addr)
        addresses.add(pa)
    return addresses


def run_module():
    module_args = dict(
        interface=dict(type='str', required=True),
        state=dict(type='str', default='present', choices=['present', 'absent'], required=False),
        addresses=dict(type='list', elements='str', required=True),
    )

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

    interface = module.params.get('interface')
    # check for correct interface type and get table
    table = get_interface_table(interface)
    if table is None:
        module.fail_json(msg=f'unsupported interface type for {interface}, only Ethernet, Vlan, PortChannel and Loopback are supported')
    # check that interface is not a VLAN member
    if is_vlan_member(config_db, interface):
        module.fail_json(msg=f'{interface } is a VLAN member')
    # check addresses and build set so current and wanted addresses can be compared
    addresses = module.params.get('addresses')
    wanted_addresses = set()
    for addr in addresses:
        try:
            pa = ipaddress.ip_interface(addr)
        except ValueError:
            module.fail_json(msg=f'{addr} is not a valid IP address')
        wanted_addresses.add(pa)
    # get current interface addresses
    current_addresses = get_current_addresses(config_db, table, interface)
    # compare addresses
    state = module.params.get('state')
    if state == 'absent':
        # when removing, only use addresses both in the database and those passed to the module
        to_update = current_addresses.intersection(wanted_addresses)
        value = None
    else:
        # when adding, only use addresses not in the database
        to_update = wanted_addresses.difference(current_addresses)
        value = {"NULL": "NULL"}
    to_update = [str(x) for x in to_update]
    changed = len(to_update) > 0
    # sonic requires an entry with just the interface as the key to apply the addresses, so add it if it's missing
    need_interface_key = False
    if interface not in config_db.get_table(table) and state == 'present':
        need_interface_key = True
        changed = True

    if module.check_mode or not changed:
        module.exit_json(changed=changed, interface=interface, addresses=to_update)
    # build keys, no need for values
    keys = list()
    for addr in to_update:
        key = (interface, addr)
        keys.append(key)

    if need_interface_key:
        config_db.set_entry(table, interface, {"NULL": "NULL"})
    for key in keys:
        config_db.set_entry(table, key, value)

    module.exit_json(changed=changed, interface=interface, addresses=to_update)


def main():
    run_module()


if __name__ == '__main__':
    main()
