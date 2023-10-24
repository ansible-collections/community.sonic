#!/usr/bin/python
#
# GNU General Public License v3.0+ (see https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import (absolute_import, division, print_function)
__metaclass__ = type


DOCUMENTATION = r'''
---
module: vlan
short_description: Configure a SONiC VLANs
version_added: "0.2.0"
description: Manage VLANs in SONiC
options:
    vlanid:
        description: The VLAN ID to configure
        required: true
        type: int
    state:
        description: Whether the VLAN should be present or absent
        default: present
        type: str
        choices: [present, absent]
    dhcp_servers:
        description: DHCP servers to relay DHCP packets to
        type: list
        elements: str
        default: []

author:
    - Erik Larsson (@whooo)
'''

EXAMPLES = r'''
# Add a VLAN
- name: Add VLAN
  community.sonic.vlan:
    vlanid: 3600

# Remove a VLAN
- name: Remove VLAN
  community.sonic.vlan:
    vlanid: 3600
    state: absent

# Add a VLAN with dhcp relay
- name: VLAN with dhcp servers
  community.sonic.vlan:
    vlanid: 3600
    dhcp_servers:
      - "10.1.0.2"
      - "10.1.0.3"
'''

RETURN = r'''
interface:
    description: The VLAN interface name
    type: str
    returned: always
'''

import ipaddress
import traceback
from ansible.module_utils.basic import AnsibleModule, missing_required_lib
from ansible_collections.community.sonic.plugins.module_utils.entries import compare_entries

try:
    from swsscommon import swsscommon
except ImportError:
    HAS_SWSSCOMMON_LIBRARY = False
    SWSSCOMMON_IMPORT_ERROR = traceback.format_exc()
else:
    HAS_SWSSCOMMON_LIBRARY = True
    SWSSCOMMON_IMPORT_ERROR = None


def check_address(address):
    """Check if an address is an IP address

    Returns False if the ipaddress module is unable to parse the address, True otherwise
    """
    try:
        ipaddress.ip_address(address)
    except ValueError:
        return False
    return True


def build_vlan_entry(vlanid, state, dhcp_servers):
    key = f'Vlan{vlanid}'
    # If state is absent there is no reason to build an entry
    if state == 'absent':
        return key, None

    val = {
        'vlanid': vlanid,
    }
    # Split dhcp_servers by IP family to reflect how the config db entry looks
    dhcpv4_servers = list()
    dhcpv6_servers = list()
    for ds in dhcp_servers:
        addr = ipaddress.ip_address(ds)
        if isinstance(addr, ipaddress.IPv6Address):
            dhcpv6_servers.append(ds)
        else:
            dhcpv4_servers.append(ds)
    if len(dhcpv4_servers):
        val["dhcp_servers"] = dhcpv4_servers
    if len(dhcpv6_servers):
        val["dhcpv6_servers"] = dhcpv6_servers
    return key, val


def run_module():
    module_args = dict(
        vlanid=dict(type='int', required=True),
        state=dict(type='str', default='present', choices=['present', 'absent'], required=False),
        dhcp_servers=dict(type='list', elements='str', default=list(), required=False),
    )

    module = AnsibleModule(
        argument_spec=module_args,
        supports_check_mode=True
    )

    # Check all addresses in dhcp_servers so we can provide an good error message
    for ds in module.params.get('dhcp_servers', []):
        if not check_address(ds):
            module.fail_json(msg=f'dhcp server address {ds} is not a valid IP address')

    if not HAS_SWSSCOMMON_LIBRARY:
        module.fail_json(
            msg=missing_required_lib('swsscommon'),
            exception=SWSSCOMMON_IMPORT_ERROR)

    config_db = swsscommon.ConfigDBConnector()
    config_db.connect()

    key, val = build_vlan_entry(**module.params)
    cur_val = config_db.get_entry('VLAN', key)
    changed = compare_entries(val, cur_val)

    if module.check_mode or not changed:
        module.exit_json(changed=changed, interface=key)

    config_db.set_entry('VLAN', key, val)

    module.exit_json(changed=changed, interface=key)


def main():
    run_module()


if __name__ == '__main__':
    main()
