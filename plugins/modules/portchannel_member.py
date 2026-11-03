#!/usr/bin/python
#
# GNU General Public License v3.0+ (see https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import (absolute_import, division, print_function)
__metaclass__ = type


DOCUMENTATION = r'''
---
module: portchannel_member
short_description: Configure SONiC PortChannel (LAG) members
version_added: "0.4.0"
description:
  - Manage the ports of a PortChannel in the C(PORTCHANNEL_MEMBER) table of the SONiC CONFIG_DB.
  - The PortChannel must exist, see M(community.sonic.portchannel).
  - Like C(config portchannel member add), the module refuses to add a port that is a VLAN member,
    carries an IP address or VRF binding, or already belongs to another PortChannel.
extends_documentation_fragment:
  - community.sonic.attributes
attributes:
  check_mode:
    support: full
  diff_mode:
    support: full
options:
    portchannel:
        description: Name of the PortChannel, C(PortChannelNNN).
        required: true
        type: str
    interface:
        description: The port to add to the PortChannel, by name (C(Ethernet0)) or alias (C(QSFP1)).
        required: true
        type: str
    state:
        description: Whether the port should be a member of the PortChannel or not.
        default: present
        type: str
        choices: [present, absent]

seealso:
  - module: community.sonic.portchannel

author:
    - Christian Svensson (@bluecmd)
'''

EXAMPLES = r'''
- name: Bundle members
  community.sonic.portchannel_member:
    portchannel: PortChannel3
    interface: "{{ item }}"
    state: present
  loop: [QSFP26/1, QSFP26/2]

- name: Remove a port from a PortChannel
  community.sonic.portchannel_member:
    portchannel: PortChannel3
    interface: Ethernet200
    state: absent
'''

RETURN = r'''
portchannel:
    description: The PortChannel name.
    type: str
    returned: always
    sample: PortChannel3
interface:
    description: The canonical name of the member port, resolved from an alias when one was given.
    type: str
    returned: always
    sample: Ethernet200
'''

from ansible.module_utils.basic import AnsibleModule
from ansible_collections.community.sonic.plugins.module_utils.config_db import (
    ConfigDB, ConfigDBError, join_key, split_key)


def build_portchannel_member_entry(portchannel, interface, state):
    """Return the ``PORTCHANNEL_MEMBER`` key and entry (``{}`` for present, ``None`` for absent)."""
    key = join_key(portchannel, interface)
    if state == 'absent':
        return key, None
    return key, {}


def membership_blockers(portchannel, port, portchannels, members, vlan_members, l3_keys):
    """Return a message explaining why ``port`` cannot join ``portchannel``, or ``None``.

    ``portchannels`` are the ``PORTCHANNEL`` keys, ``members`` the
    ``PORTCHANNEL_MEMBER`` keys, ``vlan_members`` the ``VLAN_MEMBER`` keys and
    ``l3_keys`` the ``INTERFACE`` keys. The checks mirror
    ``config portchannel member add``.
    """
    if portchannel not in portchannels:
        return 'PortChannel "%s" does not exist; create it with community.sonic.portchannel first' % portchannel
    for key in members:
        parts = split_key(key)
        if parts[1] == port and parts[0] != portchannel:
            return '%s is already a member of %s' % (port, parts[0])
    vlans = [split_key(k)[0] for k in vlan_members if split_key(k)[1] == port]
    if vlans:
        return '%s is a member of %s; remove the VLAN membership first' % (port, ', '.join(sorted(vlans)))
    if any(split_key(k)[0] == port for k in l3_keys):
        return '%s has an IP address or VRF binding in INTERFACE; remove it first' % port
    return None


def run_module():
    module_args = dict(
        portchannel=dict(type='str', required=True),
        interface=dict(type='str', required=True),
        state=dict(type='str', default='present', choices=['present', 'absent']),
    )

    module = AnsibleModule(
        argument_spec=module_args,
        supports_check_mode=True,
    )

    db = ConfigDB(module).connect()
    portchannel = module.params['portchannel']

    try:
        port = db.resolve_port(module.params['interface'])
        key, entry = build_portchannel_member_entry(portchannel, port, module.params['state'])
        if entry is not None and not db.has_entry('PORTCHANNEL_MEMBER', key):
            blocker = membership_blockers(portchannel, port, db.get_keys('PORTCHANNEL'),
                                          db.get_keys('PORTCHANNEL_MEMBER'), db.get_keys('VLAN_MEMBER'),
                                          db.get_keys('INTERFACE'))
            if blocker:
                module.fail_json(msg=blocker)
        change = db.ensure_entry('PORTCHANNEL_MEMBER', key, entry, exclusive=True)
    except ConfigDBError as e:
        module.fail_json(msg=str(e))

    module.exit_json(**change.result(portchannel=portchannel, interface=port))


def main():
    run_module()


if __name__ == '__main__':
    main()
