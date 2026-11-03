#!/usr/bin/python
#
# GNU General Public License v3.0+ (see https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import (absolute_import, division, print_function)
__metaclass__ = type


DOCUMENTATION = r'''
---
module: vxlan_map
short_description: Configure VLAN-to-VNI maps on a SONiC VXLAN tunnel
version_added: "0.4.0"
description:
  - Manage VLAN-to-VNI maps (the C(VXLAN_TUNNEL_MAP) table in CONFIG_DB) on a
    VXLAN tunnel created with M(community.sonic.vxlan_tunnel).
  - A VLAN maps to at most one VNI. When the VLAN is already mapped to another
    VNI on the tunnel, the old map is replaced. Mapping a VNI that is already
    used by another VLAN or as the L3 VNI of a VRF fails.
  - The VLAN must exist in the C(VLAN) table; create it with M(community.sonic.vlan).
extends_documentation_fragment:
  - community.sonic.attributes
attributes:
  check_mode:
    support: full
  diff_mode:
    support: full
options:
  tunnel:
    description: Name of the VXLAN tunnel the map belongs to.
    type: str
    required: true
  vlan:
    description: The VLAN ID to map.
    type: int
    required: true
  vni:
    description:
      - The VXLAN network identifier, between V(1) and V(16777215).
      - Required when O(state=present). With O(state=absent) only a map with
        this VNI is removed; without it, whatever map the VLAN has is removed.
    type: int
  state:
    description: Whether the map should be present or absent.
    type: str
    choices: [present, absent]
    default: present

author:
  - Christian Svensson (@bluecmd)
'''

EXAMPLES = r'''
- name: Stretch VLAN 100 as VNI 10100
  community.sonic.vxlan_map:
    tunnel: vtep
    vlan: 100
    vni: 10100

- name: Remove the map of VLAN 100, whatever its VNI
  community.sonic.vxlan_map:
    tunnel: vtep
    vlan: 100
    state: absent
'''

RETURN = r'''
key:
  description: The C(VXLAN_TUNNEL_MAP) key of the map.
  type: str
  returned: when the map exists before or after the run
  sample: vtep|map_10100_Vlan100
interface:
  description: The VLAN interface name.
  type: str
  returned: always
  sample: Vlan100
vni:
  description: The VNI of the map after the run.
  type: int
  returned: when O(state=present)
  sample: 10100
'''

from ansible.module_utils.basic import AnsibleModule
from ansible_collections.community.sonic.plugins.module_utils.config_db import (
    ConfigDB, ConfigDBError, build_result, join_key, normalize_entry, split_key)

MAP_TABLE = 'VXLAN_TUNNEL_MAP'
TUNNEL_TABLE = 'VXLAN_TUNNEL'
VLAN_TABLE = 'VLAN'
VRF_TABLE = 'VRF'
MIN_VNI = 1
MAX_VNI = 16777215
MIN_VLAN = 1
MAX_VLAN = 4094


def map_key(tunnel, vlan, vni):
    """Return the ``VXLAN_TUNNEL_MAP`` key SONiC uses: ``<tunnel>|map_<vni>_Vlan<vlan>``."""
    return join_key(tunnel, 'map_%d_Vlan%d' % (vni, vlan))


def build_map_entry(state, vlan, vni=None):
    """Return the ``VXLAN_TUNNEL_MAP`` entry for the given options, or ``None`` for ``state=absent``."""
    if state == 'absent':
        return None
    return {'vlan': 'Vlan%d' % vlan, 'vni': vni}


def vlan_maps(map_table, tunnel, vlan_name):
    """Return the maps (``{key: entry}``) of ``tunnel`` whose ``vlan`` field is ``vlan_name``."""
    return dict((k, v) for k, v in map_table.items()
                if split_key(k)[0] == tunnel and v.get('vlan') == vlan_name)


def run_module():
    module_args = dict(
        tunnel=dict(type='str', required=True),
        vlan=dict(type='int', required=True),
        vni=dict(type='int'),
        state=dict(type='str', default='present', choices=['present', 'absent']),
    )

    module = AnsibleModule(
        argument_spec=module_args,
        supports_check_mode=True,
        required_if=(('state', 'present', ('vni',)),),
    )
    params = module.params
    tunnel = params['tunnel']
    vlan = params['vlan']
    vni = params['vni']
    state = params['state']
    vlan_name = 'Vlan%d' % vlan

    if not (MIN_VLAN <= vlan <= MAX_VLAN):
        module.fail_json(msg='vlan must be between %d and %d, got %d' % (MIN_VLAN, MAX_VLAN, vlan))
    if vni is not None and not (MIN_VNI <= vni <= MAX_VNI):
        module.fail_json(msg='vni must be between %d and %d, got %d' % (MIN_VNI, MAX_VNI, vni))

    db = ConfigDB(module).connect()

    try:
        map_table = db.get_table(MAP_TABLE)
        existing = vlan_maps(map_table, tunnel, vlan_name)
        extra = dict(interface=vlan_name)

        if state == 'present':
            key = map_key(tunnel, vlan, vni)
            if not db.has_entry(TUNNEL_TABLE, tunnel):
                module.fail_json(msg='VXLAN tunnel "%s" does not exist; create it with community.sonic.vxlan_tunnel' % tunnel)
            if not db.has_entry(VLAN_TABLE, vlan_name):
                module.fail_json(msg='%s does not exist; create it with community.sonic.vlan' % vlan_name)
            for other_key, other in sorted(map_table.items()):
                if other_key != key and other.get('vni') == str(vni):
                    module.fail_json(msg='VNI %d is already mapped to %s (%s)' % (vni, other.get('vlan'), other_key))
            for vrf, entry in sorted(db.get_table(VRF_TABLE).items()):
                if entry.get('vni') == str(vni):
                    module.fail_json(msg='VNI %d is already used as the L3 VNI of VRF %s' % (vni, vrf))

            desired = normalize_entry(build_map_entry(state, vlan, vni))
            stale = sorted(k for k in existing if k != key)
            current = map_table.get(key)
            if key in map_table:
                before = map_table[key]
            elif stale:
                before = existing[stale[0]]
            else:
                before = {}
            changed = bool(stale) or current != desired
            if changed:
                for stale_key in stale:
                    db.delete_entry(MAP_TABLE, stale_key)
                if current != desired:
                    db.set_entry(MAP_TABLE, key, desired)
            after = desired
            extra.update(key=key, vni=vni)
        else:
            if vni is not None:
                targets = dict((k, v) for k, v in existing.items() if v.get('vni') == str(vni))
            else:
                targets = existing
            keys = sorted(targets)
            before = targets[keys[0]] if keys else {}
            after = {}
            changed = bool(keys)
            for key in keys:
                db.delete_entry(MAP_TABLE, key)
            if keys:
                extra['key'] = keys[0]
    except ConfigDBError as e:
        module.fail_json(msg=str(e))

    module.exit_json(**build_result(changed, before, after, **extra))


def main():
    run_module()


if __name__ == '__main__':
    main()
