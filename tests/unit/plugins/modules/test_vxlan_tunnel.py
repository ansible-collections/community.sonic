# -*- coding: utf-8 -*-
# GNU General Public License v3.0+ (see https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import (absolute_import, division, print_function)
__metaclass__ = type

import pytest

from ansible_collections.community.sonic.plugins.modules import vxlan_tunnel

TUNNEL = {'src_ip': '192.0.2.2'}
NVO = {'source_vtep': 'vtep'}
MAP = {'vlan': 'Vlan100', 'vni': '10100'}
MAP_KEY = 'vtep|map_10100_Vlan100'
EMPTY = {'VXLAN_TUNNEL': {}, 'VXLAN_EVPN_NVO': {}, 'VXLAN_TUNNEL_MAP': {}}


def seed_tunnel(fake_swsscommon, nvo=True, maps=False):
    data = {'VXLAN_TUNNEL': {'vtep': TUNNEL}}
    if nvo:
        data['VXLAN_EVPN_NVO'] = {'nvo': NVO}
    if maps:
        data['VXLAN_TUNNEL_MAP'] = {MAP_KEY: MAP, 'vtep|map_10200_Vlan200': {'vlan': 'Vlan200', 'vni': '10200'}}
    fake_swsscommon.seed(data)


def test_build_entries():
    assert vxlan_tunnel.build_tunnel_entry('absent') is None
    assert vxlan_tunnel.build_tunnel_entry('present', '192.0.2.2') == {'src_ip': '192.0.2.2'}
    assert vxlan_tunnel.build_nvo_entry('vtep') == {'source_vtep': 'vtep'}


def test_tunnel_maps_and_nvos():
    maps = {MAP_KEY: MAP, 'other|map_1_Vlan1': {'vlan': 'Vlan1', 'vni': '1'}}
    assert vxlan_tunnel.tunnel_maps(maps, 'vtep') == {MAP_KEY: MAP}
    nvos = {'nvo': NVO, 'nvo2': {'source_vtep': 'other'}}
    assert vxlan_tunnel.tunnel_nvos(nvos, 'vtep') == {'nvo': NVO}
    assert vxlan_tunnel.snapshot('vtep', {'vtep': TUNNEL, 'other': {}}, nvos, maps) == {
        'VXLAN_TUNNEL': {'vtep': TUNNEL}, 'VXLAN_EVPN_NVO': {'nvo': NVO}, 'VXLAN_TUNNEL_MAP': {MAP_KEY: MAP}}


@pytest.mark.parametrize('check_mode', (True, False))
def test_create_with_nvo(fake_swsscommon, run_module, check_mode):
    result = run_module(vxlan_tunnel, dict(name='vtep', source_ip='192.0.2.2', evpn_nvo='nvo'), check_mode=check_mode)
    assert result['changed'] is True
    assert result['name'] == 'vtep'
    assert result['source_ip'] == '192.0.2.2'
    assert result['evpn_nvo'] == 'nvo'
    assert result['diff'] == {
        'before': EMPTY,
        'after': {'VXLAN_TUNNEL': {'vtep': TUNNEL}, 'VXLAN_EVPN_NVO': {'nvo': NVO}, 'VXLAN_TUNNEL_MAP': {}},
    }
    if check_mode:
        assert fake_swsscommon.writes == []
        assert fake_swsscommon.has_entry('VXLAN_TUNNEL', 'vtep') is False
    else:
        assert fake_swsscommon.writes == [
            ('set_entry', 'VXLAN_TUNNEL', 'vtep', TUNNEL),
            ('set_entry', 'VXLAN_EVPN_NVO', 'nvo', NVO),
        ]
        assert fake_swsscommon.get_entry('VXLAN_TUNNEL', 'vtep') == TUNNEL
        assert fake_swsscommon.get_entry('VXLAN_EVPN_NVO', 'nvo') == NVO


def test_create_without_nvo(fake_swsscommon, run_module):
    result = run_module(vxlan_tunnel, dict(name='vtep', source_ip='192.0.2.2'))
    assert result['changed'] is True
    assert 'evpn_nvo' not in result
    assert fake_swsscommon.writes == [('set_entry', 'VXLAN_TUNNEL', 'vtep', TUNNEL)]
    assert fake_swsscommon.get_table('VXLAN_EVPN_NVO') == {}


def test_source_ip_is_normalised(fake_swsscommon, run_module):
    fake_swsscommon.seed({'VXLAN_TUNNEL': {'vtep': {'src_ip': '2001:db8::2'}}})
    result = run_module(vxlan_tunnel, dict(name='vtep', source_ip='2001:0DB8::2'))
    assert result['changed'] is False
    assert result['source_ip'] == '2001:db8::2'
    assert fake_swsscommon.writes == []


@pytest.mark.parametrize('check_mode', (True, False))
def test_idempotent(fake_swsscommon, run_module, check_mode):
    seed_tunnel(fake_swsscommon, maps=True)
    result = run_module(vxlan_tunnel, dict(name='vtep', source_ip='192.0.2.2', evpn_nvo='nvo'), check_mode=check_mode)
    assert result['changed'] is False
    assert result['evpn_nvo'] == 'nvo'
    assert result['diff']['before'] == result['diff']['after']
    assert result['diff']['after']['VXLAN_TUNNEL_MAP'] == {
        MAP_KEY: MAP, 'vtep|map_10200_Vlan200': {'vlan': 'Vlan200', 'vni': '10200'}}
    assert fake_swsscommon.writes == []


def test_existing_nvo_is_kept_when_not_given(fake_swsscommon, run_module):
    seed_tunnel(fake_swsscommon)
    result = run_module(vxlan_tunnel, dict(name='vtep', source_ip='192.0.2.2'))
    assert result['changed'] is False
    assert result['evpn_nvo'] == 'nvo'
    assert fake_swsscommon.writes == []


def test_add_nvo_to_existing_tunnel(fake_swsscommon, run_module):
    seed_tunnel(fake_swsscommon, nvo=False)
    result = run_module(vxlan_tunnel, dict(name='vtep', source_ip='192.0.2.2', evpn_nvo='nvo'))
    assert result['changed'] is True
    assert result['diff']['before']['VXLAN_EVPN_NVO'] == {}
    assert result['diff']['after']['VXLAN_EVPN_NVO'] == {'nvo': NVO}
    assert fake_swsscommon.writes == [('set_entry', 'VXLAN_EVPN_NVO', 'nvo', NVO)]


@pytest.mark.parametrize('check_mode', (True, False))
def test_change_source_ip_warns(fake_swsscommon, run_module, check_mode, monkeypatch):
    warnings = []
    monkeypatch.setattr('ansible.module_utils.basic.AnsibleModule.warn', lambda self, msg: warnings.append(msg))
    seed_tunnel(fake_swsscommon)
    result = run_module(vxlan_tunnel, dict(name='vtep', source_ip='192.0.2.3'), check_mode=check_mode)
    assert result['changed'] is True
    assert result['diff']['before']['VXLAN_TUNNEL'] == {'vtep': TUNNEL}
    assert result['diff']['after']['VXLAN_TUNNEL'] == {'vtep': {'src_ip': '192.0.2.3'}}
    assert len(warnings) == 1 and 'removed and re-created' in warnings[0]
    if check_mode:
        assert fake_swsscommon.writes == []
    else:
        assert fake_swsscommon.writes == [('set_entry', 'VXLAN_TUNNEL', 'vtep', {'src_ip': '192.0.2.3'})]


def test_second_vtep_is_refused(fake_swsscommon, run_module):
    seed_tunnel(fake_swsscommon)
    result = run_module(vxlan_tunnel, dict(name='vtep2', source_ip='192.0.2.3'), expect_failure=True)
    assert result['msg'] == ('SONiC supports a single VTEP and tunnel "vtep" (src_ip 192.0.2.2) is already configured; '
                             'manage that tunnel instead or remove it first with state=absent')
    assert fake_swsscommon.writes == []


def test_second_nvo_is_refused(fake_swsscommon, run_module):
    seed_tunnel(fake_swsscommon)
    result = run_module(vxlan_tunnel, dict(name='vtep', source_ip='192.0.2.2', evpn_nvo='nvo2'), expect_failure=True)
    assert result['msg'] == ('SONiC supports a single EVPN NVO and "nvo" (source_vtep vtep) is already configured; '
                             'use that name or remove it first')
    assert fake_swsscommon.writes == []


def test_present_requires_source_ip(fake_swsscommon, run_module):
    result = run_module(vxlan_tunnel, dict(name='vtep'), expect_failure=True)
    assert 'state is present but all of the following are missing: source_ip' in result['msg']


def test_invalid_source_ip(fake_swsscommon, run_module):
    result = run_module(vxlan_tunnel, dict(name='vtep', source_ip='loopback0'), expect_failure=True)
    assert result['msg'] == 'source_ip "loopback0" is not a valid IP address'
    assert fake_swsscommon.writes == []


def test_invalid_names(fake_swsscommon, run_module):
    result = run_module(vxlan_tunnel, dict(name='a|b', source_ip='192.0.2.2'), expect_failure=True)
    assert result['msg'] == 'tunnel name "a|b" must be non-empty and must not contain "|"'
    result = run_module(vxlan_tunnel, dict(name='vtep', source_ip='192.0.2.2', evpn_nvo=''), expect_failure=True)
    assert result['msg'] == 'evpn_nvo name "" must be non-empty and must not contain "|"'
    assert fake_swsscommon.writes == []


@pytest.mark.parametrize('check_mode', (True, False))
def test_absent_removes_nvo(fake_swsscommon, run_module, check_mode):
    seed_tunnel(fake_swsscommon)
    result = run_module(vxlan_tunnel, dict(name='vtep', state='absent'), check_mode=check_mode)
    assert result['changed'] is True
    assert result['removed_maps'] == []
    assert 'evpn_nvo' not in result
    assert result['diff'] == {
        'before': {'VXLAN_TUNNEL': {'vtep': TUNNEL}, 'VXLAN_EVPN_NVO': {'nvo': NVO}, 'VXLAN_TUNNEL_MAP': {}},
        'after': EMPTY,
    }
    if check_mode:
        assert fake_swsscommon.writes == []
        assert fake_swsscommon.has_entry('VXLAN_TUNNEL', 'vtep') is True
        assert fake_swsscommon.has_entry('VXLAN_EVPN_NVO', 'nvo') is True
    else:
        assert fake_swsscommon.writes == [
            ('set_entry', 'VXLAN_EVPN_NVO', 'nvo', None),
            ('set_entry', 'VXLAN_TUNNEL', 'vtep', None),
        ]
        assert fake_swsscommon.has_entry('VXLAN_TUNNEL', 'vtep') is False
        assert fake_swsscommon.has_entry('VXLAN_EVPN_NVO', 'nvo') is False


def test_absent_idempotent(fake_swsscommon, run_module):
    result = run_module(vxlan_tunnel, dict(name='vtep', state='absent'))
    assert result['changed'] is False
    assert result['diff'] == {'before': EMPTY, 'after': EMPTY}
    assert fake_swsscommon.writes == []


def test_absent_refuses_while_maps_exist(fake_swsscommon, run_module):
    seed_tunnel(fake_swsscommon, maps=True)
    result = run_module(vxlan_tunnel, dict(name='vtep', state='absent'), expect_failure=True)
    assert result['msg'] == ('tunnel "vtep" still has 2 VLAN-to-VNI map(s): vtep|map_10100_Vlan100, vtep|map_10200_Vlan200; '
                             'remove them with community.sonic.vxlan_map or set force=true to remove them together with the tunnel')
    assert fake_swsscommon.writes == []


@pytest.mark.parametrize('check_mode', (True, False))
def test_absent_force_cascades(fake_swsscommon, run_module, check_mode):
    seed_tunnel(fake_swsscommon, maps=True)
    result = run_module(vxlan_tunnel, dict(name='vtep', state='absent', force=True), check_mode=check_mode)
    assert result['changed'] is True
    assert result['removed_maps'] == ['vtep|map_10100_Vlan100', 'vtep|map_10200_Vlan200']
    assert result['diff']['after'] == EMPTY
    assert result['diff']['before']['VXLAN_TUNNEL_MAP'] == {
        MAP_KEY: MAP, 'vtep|map_10200_Vlan200': {'vlan': 'Vlan200', 'vni': '10200'}}
    if check_mode:
        assert fake_swsscommon.writes == []
        assert len(fake_swsscommon.get_table('VXLAN_TUNNEL_MAP')) == 2
    else:
        # maps first, then the NVO, then the tunnel
        assert fake_swsscommon.writes == [
            ('set_entry', 'VXLAN_TUNNEL_MAP', 'vtep|map_10100_Vlan100', None),
            ('set_entry', 'VXLAN_TUNNEL_MAP', 'vtep|map_10200_Vlan200', None),
            ('set_entry', 'VXLAN_EVPN_NVO', 'nvo', None),
            ('set_entry', 'VXLAN_TUNNEL', 'vtep', None),
        ]
        assert fake_swsscommon.get_table('VXLAN_TUNNEL_MAP') == {}
        assert fake_swsscommon.get_table('VXLAN_EVPN_NVO') == {}
        assert fake_swsscommon.get_table('VXLAN_TUNNEL') == {}


def test_absent_leaves_other_tunnels_maps(fake_swsscommon, run_module):
    seed_tunnel(fake_swsscommon)
    fake_swsscommon.seed({'VXLAN_TUNNEL_MAP': {'other|map_1_Vlan1': {'vlan': 'Vlan1', 'vni': '1'}}})
    result = run_module(vxlan_tunnel, dict(name='vtep', state='absent'))
    assert result['changed'] is True
    assert result['removed_maps'] == []
    assert fake_swsscommon.has_entry('VXLAN_TUNNEL_MAP', 'other|map_1_Vlan1') is True


def test_absent_refuses_while_vnet_uses_tunnel(fake_swsscommon, run_module):
    seed_tunnel(fake_swsscommon)
    fake_swsscommon.seed({'VNET': {'Vnet1': {'vxlan_tunnel': 'vtep', 'vni': '1000'}}})
    result = run_module(vxlan_tunnel, dict(name='vtep', state='absent', force=True), expect_failure=True)
    assert result['msg'] == 'tunnel "vtep" is used by VNET Vnet1; remove the VNET first'
    assert fake_swsscommon.writes == []
