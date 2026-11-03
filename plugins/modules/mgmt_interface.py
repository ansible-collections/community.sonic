#!/usr/bin/python
#
# GNU General Public License v3.0+ (see https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import (absolute_import, division, print_function)
__metaclass__ = type


DOCUMENTATION = r'''
---
module: mgmt_interface
short_description: Configure the SONiC management interface
version_added: "0.4.0"
description:
  - Manage the IP addresses and default gateways of the out-of-band management
    interface (C(eth0)) in the C(MGMT_INTERFACE) table of CONFIG_DB, and the
    physical settings of the management port in the C(MGMT_PORT) table.
  - Each address is a separate C(MGMT_INTERFACE) entry. The module only adds,
    updates or removes the entry for O(address); other addresses on the
    interface are left alone, so IPv4 and IPv6 addresses can be managed with
    separate tasks.
  - Options that are omitted are not touched. Pass an empty value
    (V('') for O(gateway) and O(description), V([]) for O(forced_mgmt_routes))
    to remove a field.
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
      - Name of the management port.
      - SONiC switches have a single management port called C(eth0).
    type: str
    default: eth0
  address:
    description:
      - IP address with prefix length, for example V(192.0.2.10/24) or
        V(2001:db8:100::12/64).
      - Required when O(state=absent). When omitted, only the C(MGMT_PORT)
        options are managed.
    type: str
  gateway:
    description:
      - Default gateway for this address, written as C(gwaddr). Must be of the
        same address family as O(address).
      - An empty string removes the gateway from an existing entry.
      - SONiC's own C(show management_interface address) command expects every
        address to have a gateway.
    type: str
  forced_mgmt_routes:
    description:
      - Destination addresses or prefixes that are always routed through the
        management interface (and the management VRF when it is enabled), even
        when a front panel route exists.
      - An empty list removes the field.
    type: list
    elements: str
  state:
    description: Whether the address should be present or absent.
    type: str
    choices: [present, absent]
    default: present
  enabled:
    description:
      - Administrative status of the management port (C(admin_status) in
        C(MGMT_PORT)). V(true) writes C(up), V(false) writes C(down).
    type: bool
  speed:
    description: Management port speed in Mbps, written to C(MGMT_PORT).
    type: int
  autoneg:
    description:
      - Enable or disable auto-negotiation on the management port
        (C(autoneg) in C(MGMT_PORT)). V(true) writes C(on), V(false) writes C(off).
    type: bool
  mtu:
    description: Management port MTU in bytes, written to C(MGMT_PORT).
    type: int
  description:
    description:
      - Description of the management port, written to C(MGMT_PORT).
      - An empty string removes the description.
    type: str
notes:
  - SONiC's C(hostcfgd) applies C(MGMT_INTERFACE) changes immediately by
    restarting the C(interfaces-config) service, which brings C(eth0) down and
    up again with the addresses from CONFIG_DB. B(If Ansible connects through
    the management interface, the SSH connection drops.) Run the task with
    C(ignore_unreachable), point C(ansible_host) at the new address if it
    changed, and reconnect with M(ansible.builtin.wait_for_connection).
  - Adding the first C(MGMT_INTERFACE) entry on a switch switches C(eth0)
    from DHCP to static addressing; a DHCP-assigned address is released.
  - The SONiC CLI keeps at most one IPv4 and one IPv6 address on C(eth0).
    This module does not enforce that limit; it manages only the entry it is
    given.
  - C(MGMT_PORT) changes are stored in CONFIG_DB and applied the next time the
    management interface is configured (for example at boot or when
    C(interfaces-config) restarts).
author:
  - Christian Svensson (@bluecmd)
'''

EXAMPLES = r'''
- name: Static IPv6 management address, reconnecting through the new address
  block:
    - name: Set the management address (drops the SSH connection when it changes)
      community.sonic.mgmt_interface:
        address: 2001:db8:100::12/64
        gateway: 2001:db8:100::1
      register: mgmt
      ignore_unreachable: true

    - name: Reconnect through the new address
      when: mgmt is changed or mgmt is unreachable
      block:
        - name: Switch the connection to the new address
          ansible.builtin.set_fact:
            ansible_host: 2001:db8:100::12

        - name: Drop the old SSH connection
          ansible.builtin.meta: reset_connection

        - name: Wait for the switch to come back
          ansible.builtin.wait_for_connection:
            delay: 5
            timeout: 120

- name: Add an IPv4 address next to the IPv6 one without a gateway
  community.sonic.mgmt_interface:
    address: 192.0.2.10/24

- name: Route a monitoring prefix through the management interface
  community.sonic.mgmt_interface:
    address: 192.0.2.10/24
    gateway: 192.0.2.1
    forced_mgmt_routes:
      - 198.51.100.0/24

- name: Remove an address
  community.sonic.mgmt_interface:
    address: 192.0.2.10/24
    state: absent

- name: Describe the management port without touching its addresses
  community.sonic.mgmt_interface:
    description: OOB to mgmt-sw1 Gi1/0/12
    enabled: true
'''

RETURN = r'''
interface:
  description: The management port name.
  type: str
  returned: always
  sample: eth0
address:
  description: The normalised address prefix, when O(address) was given.
  type: str
  returned: when address is given
  sample: 2001:db8:100::12/64
diff:
  description:
    - The CONFIG_DB entries managed by this run, before and after the change.
    - Keys are the CONFIG_DB keys (C(MGMT_INTERFACE|eth0|<prefix>) and
      C(MGMT_PORT|eth0)); an absent entry is C({}).
  type: dict
  returned: always
  contains:
    before:
      description: The managed entries before the change.
      type: dict
      returned: always
    after:
      description: The managed entries after the change.
      type: dict
      returned: always
  sample:
    before: {}
    after:
      MGMT_INTERFACE|eth0|2001:db8:100::12/64:
        gwaddr: 2001:db8:100::1
'''

import ipaddress
import re

from ansible.module_utils.basic import AnsibleModule
from ansible_collections.community.sonic.plugins.module_utils.config_db import (
    ConfigDB,
    ConfigDBError,
    bool_to_up_down,
    build_result,
    join_key,
)

MGMT_INTERFACE_TABLE = 'MGMT_INTERFACE'
MGMT_PORT_TABLE = 'MGMT_PORT'

PORT_OPTIONS = ('enabled', 'speed', 'autoneg', 'mtu', 'description')

_MGMT_PORT_RE = re.compile(r'^eth\d+$')


class ModuleError(Exception):
    """Raised for invalid parameter combinations; turned into fail_json."""


def normalize_prefix(address):
    """Return the address in the form SONiC stores it (``str(ipaddress.ip_interface(...))``).

    Raises :class:`ModuleError` for anything that is not an IP address with a prefix length.
    """
    try:
        iface = ipaddress.ip_interface(address)
    except ValueError:
        raise ModuleError('address "%s" is not a valid IP address with prefix length (for example 192.0.2.10/24)' % address)
    if '/' not in str(address):
        raise ModuleError('address "%s" must include a prefix length (for example 192.0.2.10/24 or 2001:db8::12/64)' % address)
    return str(iface), iface.version


def normalize_gateway(gateway, version):
    """Validate the gateway and check that it is of the same family as the address.

    Returns ``None`` for an empty string (remove the field) and raises
    :class:`ModuleError` for invalid or mismatched addresses.
    """
    if gateway == '':
        return None
    try:
        gw = ipaddress.ip_address(gateway)
    except ValueError:
        raise ModuleError('gateway "%s" is not a valid IP address' % gateway)
    if gw.version != version:
        raise ModuleError('gateway "%s" is IPv%d but address is IPv%d' % (gateway, gw.version, version))
    return str(gw)


def normalize_forced_routes(routes):
    """Validate the forced management routes; each may be an address or a prefix."""
    result = []
    for route in routes:
        try:
            if '/' in route:
                result.append(str(ipaddress.ip_network(route, strict=False)))
            else:
                result.append(str(ipaddress.ip_address(route)))
        except ValueError:
            raise ModuleError('forced_mgmt_routes entry "%s" is not a valid IP address or prefix' % route)
    return result


def build_address_entry(gateway, forced_mgmt_routes, version):
    """Build the desired ``MGMT_INTERFACE`` fields from the parameters.

    Only the fields that were given are included; a value of ``None`` in the
    result means "remove this field" (``ensure_entry`` semantics).
    """
    desired = {}
    if gateway is not None:
        desired['gwaddr'] = normalize_gateway(gateway, version)
    if forced_mgmt_routes is not None:
        routes = normalize_forced_routes(forced_mgmt_routes)
        desired['forced_mgmt_routes'] = routes or None
    return desired


def build_port_entry(enabled=None, speed=None, autoneg=None, mtu=None, description=None):
    """Build the desired ``MGMT_PORT`` fields from the parameters; ``None`` values mean "remove"."""
    desired = {}
    if enabled is not None:
        desired['admin_status'] = bool_to_up_down(enabled)
    if speed is not None:
        desired['speed'] = speed
    if autoneg is not None:
        desired['autoneg'] = 'on' if autoneg else 'off'
    if mtu is not None:
        desired['mtu'] = mtu
    if description is not None:
        desired['description'] = description or None
    return desired


def run_module():
    module_args = dict(
        interface=dict(type='str', default='eth0'),
        address=dict(type='str'),
        gateway=dict(type='str'),
        forced_mgmt_routes=dict(type='list', elements='str'),
        state=dict(type='str', default='present', choices=['present', 'absent']),
        enabled=dict(type='bool'),
        speed=dict(type='int'),
        autoneg=dict(type='bool'),
        mtu=dict(type='int'),
        description=dict(type='str'),
    )

    module = AnsibleModule(
        argument_spec=module_args,
        supports_check_mode=True,
        required_one_of=[['address'] + list(PORT_OPTIONS)],
        required_by={'gateway': 'address', 'forced_mgmt_routes': 'address'},
        required_if=[('state', 'absent', ['address'])],
    )
    params = module.params
    interface = params['interface']

    if not _MGMT_PORT_RE.match(interface):
        module.fail_json(msg='interface "%s" is not a management port; expected a name such as eth0' % interface)

    port_desired = build_port_entry(**dict((k, params[k]) for k in PORT_OPTIONS))

    prefix = None
    address_key = None
    address_desired = None
    try:
        if params['address'] is not None:
            prefix, version = normalize_prefix(params['address'])
            address_key = join_key(interface, prefix)
            if params['state'] == 'present':
                address_desired = build_address_entry(params['gateway'], params['forced_mgmt_routes'], version)
    except ModuleError as e:
        module.fail_json(msg=str(e))

    db = ConfigDB(module).connect()

    changed = False
    before = {}
    after = {}
    extra = dict(interface=interface)
    try:
        if address_key is not None:
            extra['address'] = prefix
            if params['state'] == 'present':
                change = db.ensure_entry(MGMT_INTERFACE_TABLE, address_key, address_desired, exclusive=False)
            else:
                change = db.ensure_absent(MGMT_INTERFACE_TABLE, address_key)
            changed = changed or change.changed
            before[join_key(MGMT_INTERFACE_TABLE, address_key)] = change.before
            after[join_key(MGMT_INTERFACE_TABLE, address_key)] = change.after
        if port_desired:
            change = db.ensure_entry(MGMT_PORT_TABLE, interface, port_desired, exclusive=False)
            changed = changed or change.changed
            before[join_key(MGMT_PORT_TABLE, interface)] = change.before
            after[join_key(MGMT_PORT_TABLE, interface)] = change.after
    except ConfigDBError as e:
        module.fail_json(msg=str(e))

    module.exit_json(**build_result(changed, before, after, **extra))


def main():
    run_module()


if __name__ == '__main__':
    main()
