#!/usr/bin/python
#
# GNU General Public License v3.0+ (see https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import (absolute_import, division, print_function)
__metaclass__ = type


DOCUMENTATION = r'''
---
module: loopback
short_description: Configure SONiC loopback interfaces
version_added: "0.4.0"
description:
  - Create and remove loopback interfaces (C(LoopbackN)) in the SONiC configuration database
    and bind them to a VRF.
  - The module manages the C(LOOPBACK_INTERFACE|LoopbackN) entry. IP addresses on the loopback
    are managed with M(community.sonic.interface_ip).
extends_documentation_fragment:
  - community.sonic.attributes
attributes:
  check_mode:
    support: full
  diff_mode:
    support: full
options:
    name:
        description: The loopback interface name, C(Loopback0) to C(Loopback999).
        required: true
        type: str
    vrf:
        description:
            - The VRF to bind the loopback interface to (C(vrf_name)).
            - The VRF must exist in the C(VRF) table, or be C(mgmt).
            - Omitting this option leaves an existing binding untouched. Pass an empty string to remove the binding.
            - SONiC's CLI removes the IP addresses of an interface before changing its VRF; bind the VRF before
              adding addresses with M(community.sonic.interface_ip).
        required: false
        type: str
    state:
        description:
            - Whether the loopback interface should be present or absent.
            - V(absent) also removes every IP address configured on the interface, as C(config loopback del) does.
        default: present
        type: str
        choices: [present, absent]

author:
    - Christian Svensson (@bluecmd)
'''

EXAMPLES = r'''
- name: Router-id / VTEP loopback
  community.sonic.loopback:
    name: Loopback0

- name: Loopback in a VRF
  community.sonic.loopback:
    name: Loopback1
    vrf: Vrf-blue

- name: Remove the VRF binding
  community.sonic.loopback:
    name: Loopback1
    vrf: ''

- name: Remove a loopback and its addresses
  community.sonic.loopback:
    name: Loopback1
    state: absent
'''

RETURN = r'''
interface:
    description: The loopback interface name.
    type: str
    returned: always
    sample: Loopback0
table:
    description: The CONFIG_DB table the entries live in.
    type: str
    returned: always
    sample: LOOPBACK_INTERFACE
addresses:
    description: The IP addresses configured on the interface after the run (before the run for O(state=absent)).
    type: list
    elements: str
    returned: always
    sample: ['192.0.2.1/32']
diff:
    description:
      - The affected C(LOOPBACK_INTERFACE) entries before and after the change, keyed by CONFIG_DB key.
      - A key missing from a side means the entry is absent on that side.
    type: dict
    returned: always
    contains:
        before:
            description: Entries before the change.
            type: dict
            returned: always
            sample: {'Loopback1': {'vrf_name': 'Vrf-blue'}, 'Loopback1|192.0.2.1/32': {}}
        after:
            description: Entries after the change.
            type: dict
            returned: always
            sample: {}
'''

from ansible.module_utils.basic import AnsibleModule
from ansible_collections.community.sonic.plugins.module_utils.config_db import (
    ConfigDB,
    ConfigDBError,
    build_result,
    join_key,
)
from ansible_collections.community.sonic.plugins.module_utils.l3_interface import (
    addresses_of,
    validate_loopback_name,
)

TABLE = 'LOOPBACK_INTERFACE'


def build_loopback_entry(current, vrf):
    """Return the desired parent entry given the current one and the ``vrf`` option.

    ``vrf=None`` keeps whatever binding is stored, ``''`` removes it and any
    other value sets ``vrf_name``.
    """
    desired = dict(current)
    if vrf is None:
        return desired
    if vrf == '':
        desired.pop('vrf_name', None)
    else:
        desired['vrf_name'] = vrf
    return desired


def vrf_exists(db, vrf):
    return vrf == 'mgmt' or db.has_entry('VRF', vrf)


def run_module():
    module_args = dict(
        name=dict(type='str', required=True),
        vrf=dict(type='str', required=False),
        state=dict(type='str', default='present', choices=['present', 'absent'], required=False),
    )

    module = AnsibleModule(
        argument_spec=module_args,
        supports_check_mode=True
    )

    vrf = module.params['vrf']
    state = module.params['state']

    try:
        name = validate_loopback_name(module.params['name'])
    except ConfigDBError as e:
        module.fail_json(msg=str(e))

    db = ConfigDB(module).connect()

    exists = db.has_entry(TABLE, name)
    current = db.get_entry(TABLE, name)
    addresses = addresses_of(db, TABLE, name)

    before = {}
    after = {}
    if exists:
        before[name] = current

    if state == 'absent':
        for prefix in addresses:
            before[join_key(name, prefix)] = {}
        changed = bool(before)
        for key in before:
            db.delete_entry(TABLE, key)
    else:
        if vrf and not vrf_exists(db, vrf):
            module.fail_json(msg='VRF "%s" does not exist' % vrf)
        desired = build_loopback_entry(current, vrf)
        after[name] = desired
        changed = not exists or desired != current
        if changed:
            db.set_entry(TABLE, name, desired)

    module.exit_json(**build_result(changed, before, after, interface=name, table=TABLE, addresses=addresses))


def main():
    run_module()


if __name__ == '__main__':
    main()
