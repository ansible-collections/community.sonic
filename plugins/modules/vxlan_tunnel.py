#!/usr/bin/python
#
# GNU General Public License v3.0+ (see https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import (absolute_import, division, print_function)
__metaclass__ = type


DOCUMENTATION = r'''
---
module: vxlan_tunnel
short_description: Configure the VXLAN tunnel endpoint (VTEP) and EVPN NVO on SONiC
version_added: "0.4.0"
description:
  - Manage the VXLAN tunnel endpoint (the C(VXLAN_TUNNEL) table in CONFIG_DB)
    and, optionally, the EVPN network virtualization overlay binding that
    points at it (the C(VXLAN_EVPN_NVO) table).
  - SONiC supports a single VTEP and a single EVPN NVO. The module refuses to
    create a second one and names the existing entry in the error message.
  - VLAN-to-VNI maps on the tunnel are managed with M(community.sonic.vxlan_map).
    A tunnel that still has maps is only removed with O(force=true), which
    removes the maps, then the NVO, then the tunnel.
  - SONiC does not change the source address of a running VTEP. When
    O(source_ip) differs from the configured address the module updates
    CONFIG_DB and warns that the tunnel has to be removed and re-created (or
    the configuration reloaded) for the new address to take effect.
extends_documentation_fragment:
  - community.sonic.attributes
attributes:
  check_mode:
    support: full
  diff_mode:
    support: full
options:
  name:
    description: Name of the VXLAN tunnel, for example V(vtep).
    type: str
    required: true
  source_ip:
    description:
      - Source IP address of the VTEP, usually the address of a loopback interface.
      - Required when O(state=present).
    type: str
  evpn_nvo:
    description:
      - Name of the EVPN NVO to bind to this tunnel, creating C(VXLAN_EVPN_NVO|<name>)
        with C(source_vtep) set to the tunnel.
      - When omitted an existing NVO is left alone. With O(state=absent) any NVO
        bound to the tunnel is removed together with the tunnel.
    type: str
  force:
    description:
      - With O(state=absent), also remove the VLAN-to-VNI maps that still
        reference the tunnel instead of failing.
    type: bool
    default: false
  state:
    description:
      - V(present) creates or updates the tunnel and, when O(evpn_nvo) is set, the NVO.
      - V(absent) removes the tunnel and the NVO bound to it. Maps on the tunnel
        block the removal unless O(force=true).
    type: str
    choices: [present, absent]
    default: present

author:
  - Christian Svensson (@bluecmd)
'''

EXAMPLES = r'''
- name: VTEP sourced from Loopback0 with an EVPN NVO
  community.sonic.vxlan_tunnel:
    name: vtep
    source_ip: 192.0.2.2
    evpn_nvo: nvo

- name: Stretch VLAN 100 as VNI 10100
  community.sonic.vxlan_map:
    tunnel: vtep
    vlan: 100
    vni: 10100

- name: Remove the VTEP, failing while VLAN-to-VNI maps exist
  community.sonic.vxlan_tunnel:
    name: vtep
    state: absent

- name: Remove the VTEP together with its maps and NVO
  community.sonic.vxlan_tunnel:
    name: vtep
    state: absent
    force: true
'''

RETURN = r'''
name:
  description: The tunnel name.
  type: str
  returned: always
  sample: vtep
source_ip:
  description: The source address as stored in CONFIG_DB.
  type: str
  returned: when O(state=present)
  sample: 192.0.2.2
evpn_nvo:
  description: Name of the EVPN NVO bound to the tunnel after the run.
  type: str
  returned: when an NVO is bound to the tunnel
  sample: nvo
removed_maps:
  description: Keys of the C(VXLAN_TUNNEL_MAP) entries removed by O(force=true).
  type: list
  elements: str
  returned: when O(state=absent)
  sample: ['vtep|map_10100_Vlan100']
diff:
  description:
    - The C(VXLAN_TUNNEL), C(VXLAN_EVPN_NVO) and C(VXLAN_TUNNEL_MAP) entries that
      belong to the tunnel, before and after the run, keyed by table and entry.
  type: dict
  returned: always
  sample:
    before: {VXLAN_TUNNEL: {}, VXLAN_EVPN_NVO: {}, VXLAN_TUNNEL_MAP: {}}
    after: {VXLAN_TUNNEL: {vtep: {src_ip: 192.0.2.2}}, VXLAN_EVPN_NVO: {nvo: {source_vtep: vtep}}, VXLAN_TUNNEL_MAP: {}}
'''

import ipaddress

from ansible.module_utils.basic import AnsibleModule
from ansible_collections.community.sonic.plugins.module_utils.config_db import (
    ConfigDB, ConfigDBError, KEY_SEPARATOR, build_result, split_key)

TUNNEL_TABLE = 'VXLAN_TUNNEL'
NVO_TABLE = 'VXLAN_EVPN_NVO'
MAP_TABLE = 'VXLAN_TUNNEL_MAP'
VNET_TABLE = 'VNET'


def build_tunnel_entry(state, source_ip=None):
    """Return the ``VXLAN_TUNNEL`` entry for the given options, or ``None`` for ``state=absent``."""
    if state == 'absent':
        return None
    return {'src_ip': source_ip}


def build_nvo_entry(tunnel):
    """Return the ``VXLAN_EVPN_NVO`` entry binding an NVO to ``tunnel``."""
    return {'source_vtep': tunnel}


def tunnel_maps(map_table, tunnel):
    """Return the ``VXLAN_TUNNEL_MAP`` entries (``{key: entry}``) that belong to ``tunnel``."""
    return dict((k, v) for k, v in map_table.items() if split_key(k)[0] == tunnel)


def tunnel_nvos(nvo_table, tunnel):
    """Return the ``VXLAN_EVPN_NVO`` entries (``{name: entry}``) whose ``source_vtep`` is ``tunnel``."""
    return dict((k, v) for k, v in nvo_table.items() if v.get('source_vtep') == tunnel)


def snapshot(tunnel, tunnel_table, nvo_table, map_table):
    """Return the diff view of everything that belongs to ``tunnel``, keyed by table."""
    return {
        TUNNEL_TABLE: dict((k, v) for k, v in tunnel_table.items() if k == tunnel),
        NVO_TABLE: tunnel_nvos(nvo_table, tunnel),
        MAP_TABLE: tunnel_maps(map_table, tunnel),
    }


def run_module():
    module_args = dict(
        name=dict(type='str', required=True),
        source_ip=dict(type='str'),
        evpn_nvo=dict(type='str'),
        force=dict(type='bool', default=False),
        state=dict(type='str', default='present', choices=['present', 'absent']),
    )

    module = AnsibleModule(
        argument_spec=module_args,
        supports_check_mode=True,
        required_if=(('state', 'present', ('source_ip',)),),
    )
    params = module.params
    name = params['name']
    nvo_name = params['evpn_nvo']
    state = params['state']

    if not name or KEY_SEPARATOR in name:
        module.fail_json(msg='tunnel name "%s" must be non-empty and must not contain "%s"' % (name, KEY_SEPARATOR))
    if nvo_name is not None and (not nvo_name or KEY_SEPARATOR in nvo_name):
        module.fail_json(msg='evpn_nvo name "%s" must be non-empty and must not contain "%s"' % (nvo_name, KEY_SEPARATOR))
    source_ip = params['source_ip']
    if source_ip is not None:
        try:
            source_ip = str(ipaddress.ip_address(source_ip))
        except ValueError:
            module.fail_json(msg='source_ip "%s" is not a valid IP address' % source_ip)

    db = ConfigDB(module).connect()

    try:
        tunnel_table = db.get_table(TUNNEL_TABLE)
        nvo_table = db.get_table(NVO_TABLE)
        map_table = db.get_table(MAP_TABLE)
        before = snapshot(name, tunnel_table, nvo_table, map_table)
        extra = dict(name=name)

        if state == 'present':
            others = sorted(k for k in tunnel_table if k != name)
            if others:
                module.fail_json(msg=(
                    'SONiC supports a single VTEP and tunnel "%s" (src_ip %s) is already configured; '
                    'manage that tunnel instead or remove it first with state=absent') % (
                    others[0], tunnel_table[others[0]].get('src_ip')))
            if nvo_name is not None:
                other_nvos = sorted(k for k in nvo_table if k != nvo_name)
                if other_nvos:
                    module.fail_json(msg=(
                        'SONiC supports a single EVPN NVO and "%s" (source_vtep %s) is already configured; '
                        'use that name or remove it first') % (
                        other_nvos[0], nvo_table[other_nvos[0]].get('source_vtep')))

            tunnel_change = db.ensure_entry(TUNNEL_TABLE, name, build_tunnel_entry(state, source_ip), exclusive=True)
            if tunnel_change.changed and tunnel_change.before:
                module.warn('source_ip of tunnel "%s" changed from %s to %s in CONFIG_DB; SONiC keeps using the old '
                            'address until the tunnel is removed and re-created or the configuration is reloaded' % (
                                name, tunnel_change.before.get('src_ip'), source_ip))
            changed = tunnel_change.changed
            after_nvos = tunnel_nvos(nvo_table, name)
            if nvo_name is not None:
                nvo_change = db.ensure_entry(NVO_TABLE, nvo_name, build_nvo_entry(name), exclusive=True)
                changed = changed or nvo_change.changed
                after_nvos = {nvo_name: nvo_change.after}
            after = {
                TUNNEL_TABLE: {name: tunnel_change.after},
                NVO_TABLE: after_nvos,
                MAP_TABLE: before[MAP_TABLE],
            }
            extra['source_ip'] = source_ip
            if after_nvos:
                extra['evpn_nvo'] = sorted(after_nvos)[0]
        else:
            maps = before[MAP_TABLE]
            nvos = before[NVO_TABLE]
            extra['removed_maps'] = []
            if name not in tunnel_table:
                changed = False
                after = before
            else:
                vnets = sorted(k for k, v in db.get_table(VNET_TABLE).items() if v.get('vxlan_tunnel') == name)
                if vnets:
                    module.fail_json(msg='tunnel "%s" is used by VNET %s; remove the VNET first' % (name, ', '.join(vnets)))
                if maps and not params['force']:
                    module.fail_json(msg=(
                        'tunnel "%s" still has %d VLAN-to-VNI map(s): %s; remove them with community.sonic.vxlan_map '
                        'or set force=true to remove them together with the tunnel') % (
                        name, len(maps), ', '.join(sorted(maps))))
                for key in sorted(maps):
                    db.delete_entry(MAP_TABLE, key)
                for key in sorted(nvos):
                    db.delete_entry(NVO_TABLE, key)
                db.delete_entry(TUNNEL_TABLE, name)
                changed = True
                after = {TUNNEL_TABLE: {}, NVO_TABLE: {}, MAP_TABLE: {}}
                extra['removed_maps'] = sorted(maps)
    except ConfigDBError as e:
        module.fail_json(msg=str(e))

    module.exit_json(**build_result(changed, before, after, **extra))


def main():
    run_module()


if __name__ == '__main__':
    main()
