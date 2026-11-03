# -*- coding: utf-8 -*-
#
# GNU General Public License v3.0+ (see https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import (absolute_import, division, print_function)
__metaclass__ = type

import pytest

from ansible_collections.community.sonic.plugins.module_utils.config_db import UnknownInterfaceError
from ansible_collections.community.sonic.plugins.modules import ntp

PORT_TABLE = {'Ethernet0': {'alias': 'QSFP1'}, 'Ethernet4': {'alias': 'QSFP2'}}

#: What init_cfg.json seeds on SONiC 202305 and later.
DEFAULT_GLOBAL = {
    'admin_state': 'enabled',
    'authentication': 'disabled',
    'dhcp': 'enabled',
    'server_role': 'disabled',
    'src_intf': 'eth0',
    'vrf': 'default',
}


def seed(fake_swsscommon, entry=None):
    fake_swsscommon.seed({'PORT': PORT_TABLE, 'NTP': {'global': DEFAULT_GLOBAL if entry is None else entry}})


# -- pure helpers ---------------------------------------------------------------

def test_build_ntp_entry():
    assert ntp.build_ntp_entry() == {}
    assert ntp.build_ntp_entry(enabled=True) == {'admin_state': 'enabled'}
    assert ntp.build_ntp_entry(enabled=False, authentication=True, dhcp=False, server_role=True,
                               source_interface='Loopback0', vrf='mgmt') == {
        'admin_state': 'disabled', 'authentication': 'enabled', 'dhcp': 'disabled', 'server_role': 'enabled',
        'src_intf': 'Loopback0', 'vrf': 'mgmt'}
    # An empty source interface removes the field
    assert ntp.build_ntp_entry(source_interface='') == {'src_intf': None}


@pytest.mark.parametrize('name,expected', (
    ('Ethernet0', 'Ethernet0'),
    ('QSFP2', 'Ethernet4'),
    ('Loopback0', 'Loopback0'),
    ('PortChannel1', 'PortChannel1'),
    ('Vlan100', 'Vlan100'),
    ('eth0', 'eth0'),
    ('eth1', 'eth1'),
    ('mgmt0', 'mgmt0'),
))
def test_resolve_source_interface(name, expected):
    assert ntp.resolve_source_interface(PORT_TABLE, {'mgmt0': {}}, name) == expected


def test_resolve_source_interface_unknown():
    with pytest.raises(UnknownInterfaceError) as excinfo:
        ntp.resolve_source_interface(PORT_TABLE, {}, 'QSFP9')
    assert 'QSFP9' in str(excinfo.value)
    with pytest.raises(UnknownInterfaceError):
        ntp.resolve_source_interface(PORT_TABLE, {}, 'mgmt0')


# -- module runs ------------------------------------------------------------------

@pytest.mark.parametrize('check_mode', (True, False))
def test_update_only_touches_given_fields(fake_swsscommon, run_module, check_mode):
    seed(fake_swsscommon)
    result = run_module(ntp, dict(dhcp=False, vrf='mgmt'), check_mode=check_mode)
    assert result['changed'] is True
    assert 'source_interface' not in result
    after = dict(DEFAULT_GLOBAL, dhcp='disabled', vrf='mgmt')
    assert result['diff'] == {'before': DEFAULT_GLOBAL, 'after': after}
    if check_mode:
        assert fake_swsscommon.writes == []
        assert fake_swsscommon.get_entry('NTP', 'global') == DEFAULT_GLOBAL
    else:
        assert fake_swsscommon.writes == [('mod_entry', 'NTP', 'global', {'dhcp': 'disabled', 'vrf': 'mgmt'})]
        assert fake_swsscommon.get_entry('NTP', 'global') == after


def test_all_options(fake_swsscommon, run_module):
    seed(fake_swsscommon)
    result = run_module(ntp, dict(enabled=False, authentication=True, dhcp=False, server_role=True,
                                  source_interface='QSFP1', vrf='mgmt'))
    assert result['changed'] is True
    assert result['source_interface'] == 'Ethernet0'
    expected = {'admin_state': 'disabled', 'authentication': 'enabled', 'dhcp': 'disabled', 'server_role': 'enabled',
                'src_intf': 'Ethernet0', 'vrf': 'mgmt'}
    assert result['diff'] == {'before': DEFAULT_GLOBAL, 'after': expected}
    assert fake_swsscommon.writes == [('mod_entry', 'NTP', 'global', expected)]
    assert fake_swsscommon.get_entry('NTP', 'global') == expected


@pytest.mark.parametrize('check_mode', (True, False))
def test_idempotent(fake_swsscommon, run_module, check_mode):
    seed(fake_swsscommon)
    result = run_module(ntp, dict(enabled=True, authentication=False, dhcp=True, server_role=False,
                                  source_interface='eth0', vrf='default'), check_mode=check_mode)
    assert result['changed'] is False
    assert result['source_interface'] == 'eth0'
    assert result['diff'] == {'before': DEFAULT_GLOBAL, 'after': DEFAULT_GLOBAL}
    assert fake_swsscommon.writes == []


def test_source_interface_loopback(fake_swsscommon, run_module):
    seed(fake_swsscommon)
    result = run_module(ntp, dict(source_interface='Loopback0'))
    assert result['changed'] is True
    assert result['source_interface'] == 'Loopback0'
    assert fake_swsscommon.writes == [('mod_entry', 'NTP', 'global', {'src_intf': 'Loopback0'})]


@pytest.mark.parametrize('check_mode', (True, False))
def test_clear_source_interface(fake_swsscommon, run_module, check_mode):
    seed(fake_swsscommon)
    result = run_module(ntp, dict(source_interface=''), check_mode=check_mode)
    assert result['changed'] is True
    assert 'source_interface' not in result
    after = dict(DEFAULT_GLOBAL)
    del after['src_intf']
    assert result['diff'] == {'before': DEFAULT_GLOBAL, 'after': after}
    if check_mode:
        assert fake_swsscommon.writes == []
        assert fake_swsscommon.get_entry('NTP', 'global') == DEFAULT_GLOBAL
    else:
        assert fake_swsscommon.writes == [('set_entry', 'NTP', 'global', after)]
        assert fake_swsscommon.get_entry('NTP', 'global') == after


def test_clear_absent_source_interface_is_noop(fake_swsscommon, run_module):
    current = {'admin_state': 'enabled', 'dhcp': 'enabled'}
    seed(fake_swsscommon, current)
    result = run_module(ntp, dict(source_interface=''))
    assert result['changed'] is False
    assert result['diff'] == {'before': current, 'after': current}
    assert fake_swsscommon.writes == []


def test_unknown_source_interface_fails(fake_swsscommon, run_module):
    seed(fake_swsscommon)
    result = run_module(ntp, dict(source_interface='QSFP9'), expect_failure=True)
    assert 'could not find interface "QSFP9"' in result['msg']
    assert fake_swsscommon.writes == []


def test_unsupported_release_fails(fake_swsscommon, run_module):
    # Releases before 202305 have NTP_SERVER keys but no NTP|global entry.
    fake_swsscommon.seed({'PORT': PORT_TABLE, 'NTP_SERVER': {'192.0.2.123': {}}})
    result = run_module(ntp, dict(dhcp=False), expect_failure=True)
    assert 'NTP|global entry does not exist' in result['msg']
    assert '202305' in result['msg']
    assert fake_swsscommon.writes == []


def test_unsupported_release_fails_in_check_mode(fake_swsscommon, run_module):
    fake_swsscommon.seed({'PORT': PORT_TABLE})
    result = run_module(ntp, dict(dhcp=False), check_mode=True, expect_failure=True)
    assert 'NTP|global entry does not exist' in result['msg']


def test_invalid_vrf_fails(fake_swsscommon, run_module):
    seed(fake_swsscommon)
    result = run_module(ntp, dict(vrf='Vrf_blue'), expect_failure=True)
    assert 'vrf' in result['msg']
    assert fake_swsscommon.writes == []


def test_at_least_one_option_is_required(fake_swsscommon, run_module):
    seed(fake_swsscommon)
    result = run_module(ntp, dict(), expect_failure=True)
    assert 'one of the following is required' in result['msg']
    assert fake_swsscommon.writes == []
