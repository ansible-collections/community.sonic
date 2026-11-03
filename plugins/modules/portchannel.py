#!/usr/bin/python
#
# GNU General Public License v3.0+ (see https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import (absolute_import, division, print_function)
__metaclass__ = type


DOCUMENTATION = r'''
---
module: portchannel
short_description: Configure SONiC PortChannels (LAG)
version_added: "0.4.0"
description:
  - Manage link aggregation groups in the C(PORTCHANNEL) table of the SONiC CONFIG_DB.
  - Use M(community.sonic.portchannel_member) to add ports to a PortChannel.
  - The module owns the whole C(PORTCHANNEL) entry; options that are not set fall back to the
    same defaults as C(config portchannel add), and I(description) is removed when omitted.
extends_documentation_fragment:
  - community.sonic.attributes
attributes:
  check_mode:
    support: full
  diff_mode:
    support: full
options:
    name:
        description:
          - Name of the PortChannel, C(PortChannelNNN).
          - SONiC limits the name to C(PortChannel) followed by up to four digits.
        required: true
        type: str
    state:
        description:
          - Whether the PortChannel should be present or absent.
          - A PortChannel that still has members, is a VLAN member or carries an IP address or VRF binding
            cannot be removed; remove those first, as C(config portchannel del) requires.
        default: present
        type: str
        choices: [present, absent]
    enabled:
        description: Administrative status of the PortChannel (C(admin_status)).
        type: bool
        default: true
    mtu:
        description: MTU of the PortChannel. Member ports must use the same MTU.
        type: int
        default: 9100
    min_links:
        description:
          - Minimum number of selected member links for the PortChannel to be up.
          - SONiC only applies this when the PortChannel is created; changing it afterwards requires
            removing and recreating the PortChannel.
        type: int
        default: 1
    fast_rate:
        description:
          - Request LACP PDUs every second instead of every 30 seconds.
          - SONiC only applies this when the PortChannel is created; changing it afterwards requires
            removing and recreating the PortChannel.
        type: bool
        default: false
    fallback:
        description:
          - Enable LACP fallback, which brings a member up without a LACP peer.
          - SONiC only applies this when the PortChannel is created; changing it afterwards requires
            removing and recreating the PortChannel.
        type: bool
        default: false
    lacp_key:
        description:
          - LACP key of the PortChannel. C(auto) derives the key from the PortChannel number.
          - SONiC only applies this when the PortChannel is created; changing it afterwards requires
            removing and recreating the PortChannel.
        type: str
        default: auto
    description:
        description:
          - Free-form description of the PortChannel. It is removed when omitted or empty.
          - This field has no C(config) CLI command and is only stored in CONFIG_DB.
        type: str

seealso:
  - module: community.sonic.portchannel_member

author:
    - Christian Svensson (@bluecmd)
'''

EXAMPLES = r'''
- name: LACP bundle towards a dual-homed peer
  community.sonic.portchannel:
    name: PortChannel3
    description: "Peering: Example Networks (AS64496)"
    fast_rate: true
    min_links: 1
    enabled: true

- name: Routed uplink bundle with a fixed LACP key
  community.sonic.portchannel:
    name: PortChannel10
    mtu: 9100
    min_links: 2
    lacp_key: 10

- name: Shut down a PortChannel
  community.sonic.portchannel:
    name: PortChannel3
    enabled: false

- name: Remove a PortChannel (remove its members first)
  community.sonic.portchannel:
    name: PortChannel3
    state: absent
'''

RETURN = r'''
interface:
    description: The PortChannel interface name.
    type: str
    returned: always
    sample: PortChannel3
'''

import re

from ansible.module_utils.basic import AnsibleModule
from ansible_collections.community.sonic.plugins.module_utils.config_db import (
    ConfigDB, ConfigDBError, bool_to_up_down, split_key)


#: SONiC requires ``PortChannel`` followed by digits and limits the kernel device name to 15 characters.
PORTCHANNEL_NAME_RE = re.compile(r'^PortChannel\d{1,4}$')
MTU_MIN = 68
MTU_MAX = 9216
LACP_KEY_MAX = 65535


def validate_params(name, mtu, min_links, lacp_key, **kwargs):
    """Return an error message for invalid option values, or ``None``."""
    if not PORTCHANNEL_NAME_RE.match(str(name)):
        return 'invalid PortChannel name "%s"; expected PortChannel followed by up to four digits' % name
    if mtu is not None and not MTU_MIN <= mtu <= MTU_MAX:
        return 'mtu %d is out of range %d-%d' % (mtu, MTU_MIN, MTU_MAX)
    if min_links is not None and min_links < 1:
        return 'min_links must be at least 1'
    if lacp_key is not None and lacp_key != 'auto':
        if not lacp_key.isdigit() or not 1 <= int(lacp_key) <= LACP_KEY_MAX:
            return 'lacp_key must be "auto" or an integer between 1 and %d' % LACP_KEY_MAX
    return None


def build_portchannel_entry(name, state, enabled, mtu, min_links, fast_rate, fallback, lacp_key, description):
    """Return the ``PORTCHANNEL`` entry for the parameters, ``None`` when ``state=absent``.

    The layout mirrors what ``config portchannel add`` writes: ``admin_status``,
    ``mtu``, ``lacp_key`` and ``min_links`` are always present, while
    ``fast_rate`` and ``fallback`` are only stored when enabled.
    """
    if state == 'absent':
        return None
    entry = {
        'admin_status': bool_to_up_down(enabled),
        'mtu': mtu,
        'min_links': min_links,
        'lacp_key': lacp_key,
    }
    if fast_rate:
        entry['fast_rate'] = True
    if fallback:
        entry['fallback'] = True
    if description:
        entry['description'] = description
    return entry


def removal_blockers(name, members, vlan_members, l3_keys):
    """Return a message explaining why ``name`` cannot be removed, or ``None``.

    ``members`` are ``PORTCHANNEL_MEMBER`` keys, ``vlan_members`` are
    ``VLAN_MEMBER`` keys and ``l3_keys`` are ``PORTCHANNEL_INTERFACE`` keys.
    """
    ports = [split_key(k)[1] for k in members if split_key(k)[0] == name]
    if ports:
        return '%s still has members %s; remove them with community.sonic.portchannel_member first' % (
            name, ', '.join(sorted(ports)))
    vlans = [split_key(k)[0] for k in vlan_members if split_key(k)[1] == name]
    if vlans:
        return '%s is still a member of %s; remove the VLAN membership first' % (name, ', '.join(sorted(vlans)))
    if any(split_key(k)[0] == name for k in l3_keys):
        return '%s still has an IP address or VRF binding in PORTCHANNEL_INTERFACE; remove it first' % name
    return None


def run_module():
    module_args = dict(
        name=dict(type='str', required=True),
        state=dict(type='str', default='present', choices=['present', 'absent']),
        enabled=dict(type='bool', default=True),
        mtu=dict(type='int', default=9100),
        min_links=dict(type='int', default=1),
        fast_rate=dict(type='bool', default=False),
        fallback=dict(type='bool', default=False),
        lacp_key=dict(type='str', default='auto', no_log=False),
        description=dict(type='str'),
    )

    module = AnsibleModule(
        argument_spec=module_args,
        supports_check_mode=True,
    )

    error = validate_params(**module.params)
    if error:
        module.fail_json(msg=error)

    db = ConfigDB(module).connect()
    name = module.params['name']
    entry = build_portchannel_entry(**module.params)

    try:
        if entry is None and db.has_entry('PORTCHANNEL', name):
            blocker = removal_blockers(name, db.get_keys('PORTCHANNEL_MEMBER'), db.get_keys('VLAN_MEMBER'),
                                       db.get_keys('PORTCHANNEL_INTERFACE'))
            if blocker:
                module.fail_json(msg=blocker)
        change = db.ensure_entry('PORTCHANNEL', name, entry, exclusive=True)
    except ConfigDBError as e:
        module.fail_json(msg=str(e))

    module.exit_json(**change.result(interface=name))


def main():
    run_module()


if __name__ == '__main__':
    main()
