# -*- coding: utf-8 -*-
# GNU General Public License v3.0+ (see https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import (absolute_import, division, print_function)
__metaclass__ = type

import pytest

from ansible_collections.community.sonic.plugins.modules import sflow_session

PORT_TABLE = {'Ethernet0': {'alias': 'QSFP1'}, 'Ethernet4': {'alias': 'QSFP2'}}
SESSION = {'admin_state': 'up', 'sample_rate': '4096', 'sample_direction': 'rx'}


def test_build_session_entry():
    assert sflow_session.build_session_entry('absent') is None
    assert sflow_session.build_session_entry('present', enabled=False) == {'admin_state': 'down'}
    assert sflow_session.build_session_entry('present', enabled=True, sample_rate=4096, sample_direction='both') == {
        'admin_state': 'up', 'sample_rate': 4096, 'sample_direction': 'both'}


@pytest.mark.parametrize('check_mode', (True, False))
def test_disable_by_alias_creates_entry(fake_swsscommon, run_module, check_mode):
    fake_swsscommon.seed({'PORT': PORT_TABLE})
    result = run_module(sflow_session, dict(interface='QSFP2', enabled=False), check_mode=check_mode)
    assert result['changed'] is True
    assert result['interface'] == 'Ethernet4'
    assert result['diff'] == {'before': {}, 'after': {'admin_state': 'down'}}
    if check_mode:
        assert fake_swsscommon.writes == []
        assert fake_swsscommon.has_entry('SFLOW_SESSION', 'Ethernet4') is False
    else:
        assert fake_swsscommon.writes == [('mod_entry', 'SFLOW_SESSION', 'Ethernet4', {'admin_state': 'down'})]
        assert fake_swsscommon.get_entry('SFLOW_SESSION', 'Ethernet4') == {'admin_state': 'down'}


def test_all_ports(fake_swsscommon, run_module):
    result = run_module(sflow_session, dict(interface='all', sample_rate=8192))
    assert result['changed'] is True
    assert result['interface'] == 'all'
    assert fake_swsscommon.writes == [('mod_entry', 'SFLOW_SESSION', 'all', {'sample_rate': '8192'})]


def test_update_only_touches_given_fields(fake_swsscommon, run_module):
    fake_swsscommon.seed({'PORT': PORT_TABLE, 'SFLOW_SESSION': {'Ethernet0': SESSION}})
    result = run_module(sflow_session, dict(interface='Ethernet0', sample_rate=512))
    assert result['changed'] is True
    assert result['diff'] == {'before': SESSION, 'after': dict(SESSION, sample_rate='512')}
    assert fake_swsscommon.writes == [('mod_entry', 'SFLOW_SESSION', 'Ethernet0', {'sample_rate': '512'})]
    assert fake_swsscommon.get_entry('SFLOW_SESSION', 'Ethernet0') == dict(SESSION, sample_rate='512')


@pytest.mark.parametrize('check_mode', (True, False))
def test_idempotent(fake_swsscommon, run_module, check_mode):
    fake_swsscommon.seed({'PORT': PORT_TABLE, 'SFLOW_SESSION': {'Ethernet0': SESSION}})
    result = run_module(sflow_session, dict(interface='QSFP1', enabled=True, sample_rate=4096, sample_direction='rx'),
                        check_mode=check_mode)
    assert result['changed'] is False
    assert result['interface'] == 'Ethernet0'
    assert result['diff'] == {'before': SESSION, 'after': SESSION}
    assert fake_swsscommon.writes == []


@pytest.mark.parametrize('check_mode', (True, False))
def test_absent(fake_swsscommon, run_module, check_mode):
    fake_swsscommon.seed({'PORT': PORT_TABLE, 'SFLOW_SESSION': {'Ethernet0': SESSION}})
    result = run_module(sflow_session, dict(interface='QSFP1', state='absent'), check_mode=check_mode)
    assert result['changed'] is True
    assert result['interface'] == 'Ethernet0'
    assert result['diff'] == {'before': SESSION, 'after': {}}
    if check_mode:
        assert fake_swsscommon.writes == []
        assert fake_swsscommon.has_entry('SFLOW_SESSION', 'Ethernet0') is True
    else:
        assert fake_swsscommon.writes == [('set_entry', 'SFLOW_SESSION', 'Ethernet0', None)]
        assert fake_swsscommon.has_entry('SFLOW_SESSION', 'Ethernet0') is False


def test_absent_idempotent(fake_swsscommon, run_module):
    fake_swsscommon.seed({'PORT': PORT_TABLE})
    result = run_module(sflow_session, dict(interface='Ethernet0', state='absent'))
    assert result['changed'] is False
    assert result['diff'] == {'before': {}, 'after': {}}
    assert fake_swsscommon.writes == []


def test_present_requires_an_option(fake_swsscommon, run_module):
    fake_swsscommon.seed({'PORT': PORT_TABLE})
    result = run_module(sflow_session, dict(interface='Ethernet0'), expect_failure=True)
    assert 'state is present but any of the following are missing' in result['msg']
    assert fake_swsscommon.writes == []


@pytest.mark.parametrize('value', (0, 255, 8388609))
def test_invalid_sample_rate(fake_swsscommon, run_module, value):
    fake_swsscommon.seed({'PORT': PORT_TABLE})
    result = run_module(sflow_session, dict(interface='Ethernet0', sample_rate=value), expect_failure=True)
    assert result['msg'] == 'sample_rate must be between 256 and 8388608, got %d' % value
    assert fake_swsscommon.writes == []


@pytest.mark.parametrize('name', ('QSFP9', 'PortChannel1', 'Vlan100'))
def test_unknown_interface(fake_swsscommon, run_module, name):
    fake_swsscommon.seed({'PORT': PORT_TABLE})
    result = run_module(sflow_session, dict(interface=name, enabled=False), expect_failure=True)
    assert result['msg'] == 'could not find interface "%s"' % name
    assert fake_swsscommon.writes == []
