#!/usr/bin/python
#
# GNU General Public License v3.0+ (see https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import (absolute_import, division, print_function)
__metaclass__ = type


DOCUMENTATION = r'''
---
module: interface_ip
short_description: Configure IP addresses on SONiC L3 interfaces
version_added: "0.4.0"
description:
  - Add and remove IPv4 and IPv6 addresses on Ethernet, PortChannel, VLAN and Loopback interfaces.
  - The table is chosen from the interface name, C(INTERFACE) for C(EthernetN), C(PORTCHANNEL_INTERFACE)
    for C(PortChannelN), C(VLAN_INTERFACE) for C(VlanN) and C(LOOPBACK_INTERFACE) for C(LoopbackN).
    Each address is an C(<interface>|<prefix>) entry in that table.
  - Adding the first address also creates the interface's parent entry (C(<interface>)) in the table, which
    SONiC needs before it configures any address. Removing the last address leaves the parent entry alone
    unless O(remove_parent=true).
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
            - The interface to configure. Port aliases are accepted for Ethernet ports.
            - With O(state=present) a PortChannel or VLAN interface must exist in the C(PORTCHANNEL) or C(VLAN)
              table; a Loopback is created on demand.
        required: true
        type: str
    address:
        description:
            - The IPv4 or IPv6 address with prefix length, for example V(192.0.2.1/31) or V(2001:db8::1/64).
            - The address is stored in canonical form (compressed IPv6), so spelling differences do not cause changes.
        required: true
        type: str
    remove_parent:
        description:
            - With O(state=absent), also remove the interface's parent entry from the table when the removed
              address was the last one. This is what C(config loopback del) does for loopbacks; for other
              interfaces it turns the interface back into a pure L2 port.
            - The parent entry is kept when other addresses remain, regardless of this option.
        default: false
        type: bool
    state:
        description: Whether the address should be present or absent on the interface.
        default: present
        type: str
        choices: [present, absent]
notes:
  - SONiC does not allow IP addresses on a port that is a member of a VLAN or a PortChannel; the module fails
    with a clear message instead of writing such an entry.

author:
    - Christian Svensson (@bluecmd)
'''

EXAMPLES = r'''
- name: Router-id / VTEP loopback address
  community.sonic.interface_ip:
    interface: Loopback0
    address: 192.0.2.2/32

- name: Routed uplink on a port, by alias
  community.sonic.interface_ip:
    interface: QSFP1
    address: 198.51.100.1/31

- name: Addresses on several interfaces
  community.sonic.interface_ip:
    interface: "{{ item.interface }}"
    address: "{{ item.address }}"
  loop:
    - { interface: PortChannel2, address: 198.51.100.1/31 }
    - { interface: Vlan100, address: 203.0.113.2/24 }
    - { interface: Vlan100, address: '2001:db8:100::2/64' }

- name: Remove an address and the L3 entry of the port once no addresses remain
  community.sonic.interface_ip:
    interface: Ethernet24
    address: 198.51.100.1/31
    state: absent
    remove_parent: true
'''

RETURN = r'''
interface:
    description: The resolved interface name.
    type: str
    returned: always
    sample: Ethernet24
address:
    description: The address in canonical form, as stored in CONFIG_DB.
    type: str
    returned: always
    sample: 2001:db8::1/64
table:
    description: The CONFIG_DB table holding the interface's addresses.
    type: str
    returned: always
    sample: INTERFACE
addresses:
    description: All addresses configured on the interface after the run.
    type: list
    elements: str
    returned: always
    sample: ['192.0.2.1/31', '2001:db8::1/64']
parent_created:
    description: Whether the interface's parent entry was (or in check mode, would be) created by this run.
    type: bool
    returned: always
parent_removed:
    description: Whether the interface's parent entry was (or in check mode, would be) removed by this run.
    type: bool
    returned: always
diff:
    description:
      - The affected entries of the table before and after the change, keyed by CONFIG_DB key.
      - A key missing from a side means the entry is absent on that side.
    type: dict
    returned: always
    contains:
        before:
            description: Entries before the change.
            type: dict
            returned: always
            sample: {}
        after:
            description: Entries after the change.
            type: dict
            returned: always
            sample: {'Loopback1': {}, 'Loopback1|192.0.2.1/32': {}}
'''

from ansible.module_utils.basic import AnsibleModule
from ansible_collections.community.sonic.plugins.module_utils.config_db import (
    ConfigDB,
    ConfigDBError,
    build_result,
    interface_kind,
    interface_table,
    join_key,
    l3_interface_table,
)
from ansible_collections.community.sonic.plugins.module_utils.l3_interface import (
    addresses_of,
    member_of,
    normalize_prefix,
    validate_loopback_name,
)


def check_interface_usable(db, interface):
    """Raise ``ConfigDBError`` if ``interface`` cannot carry IP addresses.

    Ethernet ports are resolved before this is called, so they exist. PortChannel
    and VLAN interfaces must be defined; a port or PortChannel that is a member
    of a VLAN or PortChannel cannot have addresses.
    """
    kind = interface_kind(interface)
    if kind == 'Loopback':
        validate_loopback_name(interface)
    if kind in ('PortChannel', 'Vlan') and not db.has_entry(interface_table(interface), interface):
        raise ConfigDBError('interface "%s" does not exist' % interface)
    if kind in ('Ethernet', 'PortChannel'):
        parent = member_of(db, interface)
        if parent is not None:
            raise ConfigDBError('interface "%s" is a member of %s and cannot have an IP address' % (interface, parent))


def run_module():
    module_args = dict(
        interface=dict(type='str', required=True),
        address=dict(type='str', required=True),
        remove_parent=dict(type='bool', default=False, required=False),
        state=dict(type='str', default='present', choices=['present', 'absent'], required=False),
    )

    module = AnsibleModule(
        argument_spec=module_args,
        supports_check_mode=True
    )

    state = module.params['state']
    remove_parent = module.params['remove_parent']

    try:
        address = normalize_prefix(module.params['address'])
    except ConfigDBError as e:
        module.fail_json(msg=str(e))

    db = ConfigDB(module).connect()

    try:
        interface = db.resolve_interface(module.params['interface'])
        table = l3_interface_table(interface)
        if state == 'present':
            check_interface_usable(db, interface)
    except ConfigDBError as e:
        module.fail_json(msg=str(e))

    key = join_key(interface, address)
    parent_exists = db.has_entry(table, interface)
    parent_entry = db.get_entry(table, interface)
    address_exists = db.has_entry(table, key)
    addresses = addresses_of(db, table, interface)

    before = {}
    after = {}
    parent_created = False
    parent_removed = False

    if state == 'present':
        if not parent_exists:
            parent_created = True
            after[interface] = {}
            db.set_entry(table, interface, {})
        if not address_exists:
            after[key] = {}
            db.set_entry(table, key, {})
            addresses = sorted(addresses + [address])
    else:
        if address_exists:
            before[key] = {}
            db.delete_entry(table, key)
            addresses = [a for a in addresses if a != address]
        if remove_parent and parent_exists and not addresses:
            parent_removed = True
            before[interface] = parent_entry
            db.delete_entry(table, interface)

    changed = bool(before) or bool(after)
    module.exit_json(**build_result(
        changed, before, after,
        interface=interface, address=address, table=table, addresses=addresses,
        parent_created=parent_created, parent_removed=parent_removed))


def main():
    run_module()


if __name__ == '__main__':
    main()
