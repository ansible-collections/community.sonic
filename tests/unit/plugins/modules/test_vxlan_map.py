# -*- coding: utf-8 -*-
# GNU General Public License v3.0+ (see https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import (absolute_import, division, print_function)
__metaclass__ = type

import pytest

from ansible_collections.community.sonic.plugins.modules import vxlan_map

MAP = {'vlan': 'Vlan100', 'vni': '10100'}
MAP_KEY = 'vtep|map_10100_Vlan100'
BASE = {
    'VXLAN_TUNNEL': {'vtep': {'src_ip': '192.0.2.2'}},
    'VLAN': {'Vlan100': {'vlanid': '100'}, 'Vlan200': {'vlanid': '200'}},
}


def test_helpers():
    assert vxlan_map.map_key('vtep', 100, 10100) == MAP_KEY
    assert vxlan_map.build_map_entry('absent', 100) is None
    assert vxlan_map.build_map_entry('present', 100, 10100) == {'vlan': 'Vlan100', 'vni': 10100}
    maps = {MAP_KEY: MAP, 'vtep|map_10200_Vlan200': {'vlan': 'Vlan200', 'vni': '10200'},
            'other|map_1_Vlan100': {'vlan': 'Vlan100', 'vni': '1'}}
    assert vxlan_map.vlan_maps(maps, 'vtep', 'Vlan100') == {MAP_KEY: MAP}


@pytest.mark.parametrize('check_mode', (True, False))
def test_create(fake_swsscommon, run_module, check_mode):
    fake_swsscommon.seed(BASE)
    result = run_module(vxlan_map, dict(tunnel='vtep', vlan=100, vni=10100), check_mode=check_mode)
    assert result['changed'] is True
    assert result['key'] == MAP_KEY
    assert result['interface'] == 'Vlan100'
    assert result['vni'] == 10100
    assert result['diff'] == {'before': {}, 'after': MAP}
    if check_mode:
        assert fake_swsscommon.writes == []
        assert fake_swsscommon.has_entry('VXLAN_TUNNEL_MAP', MAP_KEY) is False
    else:
        assert fake_swsscommon.writes == [('set_entry', 'VXLAN_TUNNEL_MAP', MAP_KEY, MAP)]
        assert fake_swsscommon.get_entry('VXLAN_TUNNEL_MAP', MAP_KEY) == MAP


@pytest.mark.parametrize('check_mode', (True, False))
def test_idempotent(fake_swsscommon, run_module, check_mode):
    fake_swsscommon.seed(BASE)
    fake_swsscommon.seed({'VXLAN_TUNNEL_MAP': {MAP_KEY: MAP}})
    result = run_module(vxlan_map, dict(tunnel='vtep', vlan=100, vni=10100), check_mode=check_mode)
    assert result['changed'] is False
    assert result['key'] == MAP_KEY
    assert result['diff'] == {'before': MAP, 'after': MAP}
    assert fake_swsscommon.writes == []


@pytest.mark.parametrize('check_mode', (True, False))
def test_change_vni_replaces_map(fake_swsscommon, run_module, check_mode):
    fake_swsscommon.seed(BASE)
    fake_swsscommon.seed({'VXLAN_TUNNEL_MAP': {MAP_KEY: MAP}})
    result = run_module(vxlan_map, dict(tunnel='vtep', vlan=100, vni=10101), check_mode=check_mode)
    new_key = 'vtep|map_10101_Vlan100'
    new_map = {'vlan': 'Vlan100', 'vni': '10101'}
    assert result['changed'] is True
    assert result['key'] == new_key
    assert result['diff'] == {'before': MAP, 'after': new_map}
    if check_mode:
        assert fake_swsscommon.writes == []
        assert fake_swsscommon.get_table('VXLAN_TUNNEL_MAP') == {MAP_KEY: MAP}
    else:
        assert fake_swsscommon.writes == [
            ('set_entry', 'VXLAN_TUNNEL_MAP', MAP_KEY, None),
            ('set_entry', 'VXLAN_TUNNEL_MAP', new_key, new_map),
        ]
        assert fake_swsscommon.get_table('VXLAN_TUNNEL_MAP') == {new_key: new_map}


def test_present_requires_vni(fake_swsscommon, run_module):
    result = run_module(vxlan_map, dict(tunnel='vtep', vlan=100), expect_failure=True)
    assert 'state is present but all of the following are missing: vni' in result['msg']


@pytest.mark.parametrize('vni', (0, 16777216))
def test_invalid_vni(fake_swsscommon, run_module, vni):
    fake_swsscommon.seed(BASE)
    result = run_module(vxlan_map, dict(tunnel='vtep', vlan=100, vni=vni), expect_failure=True)
    assert result['msg'] == 'vni must be between 1 and 16777215, got %d' % vni
    assert fake_swsscommon.writes == []


@pytest.mark.parametrize('vlan', (0, 4095))
def test_invalid_vlan(fake_swsscommon, run_module, vlan):
    fake_swsscommon.seed(BASE)
    result = run_module(vxlan_map, dict(tunnel='vtep', vlan=vlan, vni=10100), expect_failure=True)
    assert result['msg'] == 'vlan must be between 1 and 4094, got %d' % vlan
    assert fake_swsscommon.writes == []


def test_missing_tunnel(fake_swsscommon, run_module):
    fake_swsscommon.seed({'VLAN': BASE['VLAN']})
    result = run_module(vxlan_map, dict(tunnel='vtep', vlan=100, vni=10100), expect_failure=True)
    assert result['msg'] == 'VXLAN tunnel "vtep" does not exist; create it with community.sonic.vxlan_tunnel'
    assert fake_swsscommon.writes == []


def test_missing_vlan(fake_swsscommon, run_module):
    fake_swsscommon.seed(BASE)
    result = run_module(vxlan_map, dict(tunnel='vtep', vlan=300, vni=10300), expect_failure=True)
    assert result['msg'] == 'Vlan300 does not exist; create it with community.sonic.vlan'
    assert fake_swsscommon.writes == []


def test_vni_already_mapped_to_other_vlan(fake_swsscommon, run_module):
    fake_swsscommon.seed(BASE)
    fake_swsscommon.seed({'VXLAN_TUNNEL_MAP': {MAP_KEY: MAP}})
    result = run_module(vxlan_map, dict(tunnel='vtep', vlan=200, vni=10100), expect_failure=True)
    assert result['msg'] == 'VNI 10100 is already mapped to Vlan100 (vtep|map_10100_Vlan100)'
    assert fake_swsscommon.writes == []


def test_vni_used_by_vrf(fake_swsscommon, run_module):
    fake_swsscommon.seed(BASE)
    fake_swsscommon.seed({'VRF': {'Vrf1': {'vni': '10100'}}})
    result = run_module(vxlan_map, dict(tunnel='vtep', vlan=100, vni=10100), expect_failure=True)
    assert result['msg'] == 'VNI 10100 is already used as the L3 VNI of VRF Vrf1'
    assert fake_swsscommon.writes == []


@pytest.mark.parametrize('check_mode', (True, False))
def test_absent(fake_swsscommon, run_module, check_mode):
    fake_swsscommon.seed(BASE)
    fake_swsscommon.seed({'VXLAN_TUNNEL_MAP': {MAP_KEY: MAP}})
    result = run_module(vxlan_map, dict(tunnel='vtep', vlan=100, state='absent'), check_mode=check_mode)
    assert result['changed'] is True
    assert result['key'] == MAP_KEY
    assert result['interface'] == 'Vlan100'
    assert 'vni' not in result
    assert result['diff'] == {'before': MAP, 'after': {}}
    if check_mode:
        assert fake_swsscommon.writes == []
        assert fake_swsscommon.has_entry('VXLAN_TUNNEL_MAP', MAP_KEY) is True
    else:
        assert fake_swsscommon.writes == [('set_entry', 'VXLAN_TUNNEL_MAP', MAP_KEY, None)]
        assert fake_swsscommon.has_entry('VXLAN_TUNNEL_MAP', MAP_KEY) is False


def test_absent_with_matching_vni(fake_swsscommon, run_module):
    fake_swsscommon.seed({'VXLAN_TUNNEL_MAP': {MAP_KEY: MAP}})
    result = run_module(vxlan_map, dict(tunnel='vtep', vlan=100, vni=10100, state='absent'))
    assert result['changed'] is True
    assert fake_swsscommon.writes == [('set_entry', 'VXLAN_TUNNEL_MAP', MAP_KEY, None)]


def test_absent_with_other_vni_is_noop(fake_swsscommon, run_module):
    fake_swsscommon.seed({'VXLAN_TUNNEL_MAP': {MAP_KEY: MAP}})
    result = run_module(vxlan_map, dict(tunnel='vtep', vlan=100, vni=10101, state='absent'))
    assert result['changed'] is False
    assert 'key' not in result
    assert result['diff'] == {'before': {}, 'after': {}}
    assert fake_swsscommon.writes == []


def test_absent_idempotent(fake_swsscommon, run_module):
    result = run_module(vxlan_map, dict(tunnel='vtep', vlan=100, state='absent'))
    assert result['changed'] is False
    assert result['diff'] == {'before': {}, 'after': {}}
    assert fake_swsscommon.writes == []


def test_absent_leaves_other_tunnel_alone(fake_swsscommon, run_module):
    fake_swsscommon.seed({'VXLAN_TUNNEL_MAP': {'other|map_10100_Vlan100': MAP}})
    result = run_module(vxlan_map, dict(tunnel='vtep', vlan=100, state='absent'))
    assert result['changed'] is False
    assert fake_swsscommon.writes == []
