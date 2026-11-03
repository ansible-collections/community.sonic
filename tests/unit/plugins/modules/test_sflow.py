# -*- coding: utf-8 -*-
# GNU General Public License v3.0+ (see https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import (absolute_import, division, print_function)
__metaclass__ = type

import pytest

from ansible_collections.community.sonic.plugins.module_utils.config_db import UnknownInterfaceError
from ansible_collections.community.sonic.plugins.modules import sflow

PORT_TABLE = {'Ethernet0': {'alias': 'QSFP1'}, 'Ethernet4': {'alias': 'QSFP2'}}
GLOBAL = {'admin_state': 'up', 'agent_id': 'eth0', 'polling_interval': '20', 'sample_direction': 'rx'}


def test_build_sflow_entry():
    assert sflow.build_sflow_entry('absent') is None
    assert sflow.build_sflow_entry('present', enabled=True) == {'admin_state': 'up'}
    assert sflow.build_sflow_entry('present', enabled=False, agent_id='Loopback0', polling_interval=0,
                                   sample_direction='both') == {
        'admin_state': 'down', 'agent_id': 'Loopback0', 'polling_interval': 0, 'sample_direction': 'both'}
    # An empty agent_id removes the field
    assert sflow.build_sflow_entry('present', agent_id='') == {'agent_id': None}


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
def test_resolve_agent_interface(name, expected):
    assert sflow.resolve_agent_interface(PORT_TABLE, {'mgmt0': {}}, name) == expected


def test_resolve_agent_interface_unknown():
    with pytest.raises(UnknownInterfaceError):
        sflow.resolve_agent_interface(PORT_TABLE, {}, 'QSFP9')
    with pytest.raises(UnknownInterfaceError):
        sflow.resolve_agent_interface(PORT_TABLE, {}, 'mgmt0')


@pytest.mark.parametrize('check_mode', (True, False))
def test_enable_creates_entry(fake_swsscommon, run_module, check_mode):
    fake_swsscommon.seed({'PORT': PORT_TABLE})
    result = run_module(sflow, dict(enabled=True, agent_id='QSFP1', sample_direction='rx'), check_mode=check_mode)
    assert result['changed'] is True
    assert result['agent_id'] == 'Ethernet0'
    assert result['diff'] == {'before': {}, 'after': {'admin_state': 'up', 'agent_id': 'Ethernet0', 'sample_direction': 'rx'}}
    if check_mode:
        assert fake_swsscommon.writes == []
        assert fake_swsscommon.has_entry('SFLOW', 'global') is False
    else:
        assert fake_swsscommon.writes == [('mod_entry', 'SFLOW', 'global',
                                           {'admin_state': 'up', 'agent_id': 'Ethernet0', 'sample_direction': 'rx'})]
        assert fake_swsscommon.get_entry('SFLOW', 'global') == {'admin_state': 'up', 'agent_id': 'Ethernet0', 'sample_direction': 'rx'}


def test_update_only_touches_given_fields(fake_swsscommon, run_module):
    fake_swsscommon.seed({'SFLOW': {'global': GLOBAL}})
    result = run_module(sflow, dict(enabled=False, polling_interval=30))
    assert result['changed'] is True
    assert 'agent_id' not in result
    assert result['diff']['before'] == GLOBAL
    assert result['diff']['after'] == dict(GLOBAL, admin_state='down', polling_interval='30')
    assert fake_swsscommon.writes == [('mod_entry', 'SFLOW', 'global', {'admin_state': 'down', 'polling_interval': '30'})]
    assert fake_swsscommon.get_entry('SFLOW', 'global') == dict(GLOBAL, admin_state='down', polling_interval='30')


@pytest.mark.parametrize('check_mode', (True, False))
def test_idempotent(fake_swsscommon, run_module, check_mode):
    fake_swsscommon.seed({'SFLOW': {'global': GLOBAL}})
    result = run_module(sflow, dict(enabled=True, agent_id='eth0', polling_interval=20, sample_direction='rx'),
                        check_mode=check_mode)
    assert result['changed'] is False
    assert result['diff'] == {'before': GLOBAL, 'after': GLOBAL}
    assert fake_swsscommon.writes == []


@pytest.mark.parametrize('check_mode', (True, False))
def test_clear_agent_id(fake_swsscommon, run_module, check_mode):
    fake_swsscommon.seed({'SFLOW': {'global': GLOBAL}})
    result = run_module(sflow, dict(agent_id=''), check_mode=check_mode)
    assert result['changed'] is True
    assert 'agent_id' not in result
    after = dict(GLOBAL)
    del after['agent_id']
    assert result['diff'] == {'before': GLOBAL, 'after': after}
    if check_mode:
        assert fake_swsscommon.writes == []
    else:
        assert fake_swsscommon.writes == [('set_entry', 'SFLOW', 'global', after)]
        assert fake_swsscommon.get_entry('SFLOW', 'global') == after


def test_clear_absent_agent_id_is_noop(fake_swsscommon, run_module):
    current = {'admin_state': 'up', 'polling_interval': '20'}
    fake_swsscommon.seed({'SFLOW': {'global': current}})
    result = run_module(sflow, dict(agent_id=''))
    assert result['changed'] is False
    assert result['diff'] == {'before': current, 'after': current}
    assert fake_swsscommon.writes == []


@pytest.mark.parametrize('check_mode', (True, False))
def test_absent(fake_swsscommon, run_module, check_mode):
    fake_swsscommon.seed({'SFLOW': {'global': GLOBAL}})
    result = run_module(sflow, dict(state='absent'), check_mode=check_mode)
    assert result['changed'] is True
    assert result['diff'] == {'before': GLOBAL, 'after': {}}
    if check_mode:
        assert fake_swsscommon.writes == []
        assert fake_swsscommon.has_entry('SFLOW', 'global') is True
    else:
        assert fake_swsscommon.writes == [('set_entry', 'SFLOW', 'global', None)]
        assert fake_swsscommon.has_entry('SFLOW', 'global') is False


def test_absent_idempotent(fake_swsscommon, run_module):
    result = run_module(sflow, dict(state='absent'))
    assert result['changed'] is False
    assert result['diff'] == {'before': {}, 'after': {}}
    assert fake_swsscommon.writes == []


def test_present_requires_an_option(fake_swsscommon, run_module):
    result = run_module(sflow, dict(), expect_failure=True)
    assert 'state is present but any of the following are missing' in result['msg']
    assert fake_swsscommon.writes == []


@pytest.mark.parametrize('value', (1, 4, 301, -1))
def test_invalid_polling_interval(fake_swsscommon, run_module, value):
    result = run_module(sflow, dict(polling_interval=value), expect_failure=True)
    assert result['msg'] == 'polling_interval must be 0 or between 5 and 300, got %d' % value
    assert fake_swsscommon.writes == []


def test_unknown_agent_interface(fake_swsscommon, run_module):
    fake_swsscommon.seed({'PORT': PORT_TABLE})
    result = run_module(sflow, dict(enabled=True, agent_id='QSFP9'), expect_failure=True)
    assert result['msg'] == 'could not find interface "QSFP9" to use as the sFlow agent'
    assert fake_swsscommon.writes == []
