# -*- coding: utf-8 -*-
# GNU General Public License v3.0+ (see https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import (absolute_import, division, print_function)
__metaclass__ = type

import pytest

from ansible_collections.community.sonic.plugins.modules import sflow_collector

COLLECTOR = {'collector_ip': '2001:db8::18', 'collector_port': '6343', 'collector_vrf': 'mgmt'}


def test_build_collector_entry():
    assert sflow_collector.build_collector_entry('absent') is None
    assert sflow_collector.build_collector_entry('present', '192.0.2.1') == {
        'collector_ip': '192.0.2.1', 'collector_port': 6343, 'collector_vrf': 'default'}
    assert sflow_collector.build_collector_entry('present', '2001:db8::18', 6344, 'mgmt') == {
        'collector_ip': '2001:db8::18', 'collector_port': 6344, 'collector_vrf': 'mgmt'}


@pytest.mark.parametrize('check_mode', (True, False))
def test_create(fake_swsscommon, run_module, check_mode):
    result = run_module(sflow_collector, dict(name='flow-collector', address='2001:db8::18', vrf='mgmt'),
                        check_mode=check_mode)
    assert result['changed'] is True
    assert result['name'] == 'flow-collector'
    assert result['diff'] == {'before': {}, 'after': COLLECTOR}
    if check_mode:
        assert fake_swsscommon.writes == []
        assert fake_swsscommon.has_entry('SFLOW_COLLECTOR', 'flow-collector') is False
    else:
        assert fake_swsscommon.writes == [('set_entry', 'SFLOW_COLLECTOR', 'flow-collector', COLLECTOR)]
        assert fake_swsscommon.get_entry('SFLOW_COLLECTOR', 'flow-collector') == COLLECTOR


@pytest.mark.parametrize('check_mode', (True, False))
def test_update(fake_swsscommon, run_module, check_mode):
    fake_swsscommon.seed({'SFLOW_COLLECTOR': {'flow-collector': COLLECTOR}})
    result = run_module(sflow_collector, dict(name='flow-collector', address='192.0.2.18', port=6344),
                        check_mode=check_mode)
    after = {'collector_ip': '192.0.2.18', 'collector_port': '6344', 'collector_vrf': 'default'}
    assert result['changed'] is True
    assert result['diff'] == {'before': COLLECTOR, 'after': after}
    if check_mode:
        assert fake_swsscommon.writes == []
        assert fake_swsscommon.get_entry('SFLOW_COLLECTOR', 'flow-collector') == COLLECTOR
    else:
        assert fake_swsscommon.writes == [('set_entry', 'SFLOW_COLLECTOR', 'flow-collector', after)]
        assert fake_swsscommon.get_entry('SFLOW_COLLECTOR', 'flow-collector') == after


def test_legacy_entry_without_vrf_gets_default(fake_swsscommon, run_module):
    fake_swsscommon.seed({'SFLOW_COLLECTOR': {'old': {'collector_ip': '192.0.2.1', 'collector_port': '6343'}}})
    result = run_module(sflow_collector, dict(name='old', address='192.0.2.1'))
    assert result['changed'] is True
    assert result['diff']['after'] == {'collector_ip': '192.0.2.1', 'collector_port': '6343', 'collector_vrf': 'default'}


@pytest.mark.parametrize('check_mode', (True, False))
def test_idempotent(fake_swsscommon, run_module, check_mode):
    fake_swsscommon.seed({'SFLOW_COLLECTOR': {'flow-collector': COLLECTOR}})
    result = run_module(sflow_collector, dict(name='flow-collector', address='2001:db8::18', port=6343, vrf='mgmt'),
                        check_mode=check_mode)
    assert result['changed'] is False
    assert result['diff'] == {'before': COLLECTOR, 'after': COLLECTOR}
    assert fake_swsscommon.writes == []


def test_address_is_normalised(fake_swsscommon, run_module):
    fake_swsscommon.seed({'SFLOW_COLLECTOR': {'flow-collector': COLLECTOR}})
    result = run_module(sflow_collector, dict(name='flow-collector', address='2001:0db8:0000::18', vrf='mgmt'))
    assert result['changed'] is False
    assert fake_swsscommon.writes == []


@pytest.mark.parametrize('check_mode', (True, False))
def test_absent(fake_swsscommon, run_module, check_mode):
    fake_swsscommon.seed({'SFLOW_COLLECTOR': {'flow-collector': COLLECTOR}})
    result = run_module(sflow_collector, dict(name='flow-collector', state='absent'), check_mode=check_mode)
    assert result['changed'] is True
    assert result['name'] == 'flow-collector'
    assert result['diff'] == {'before': COLLECTOR, 'after': {}}
    if check_mode:
        assert fake_swsscommon.writes == []
        assert fake_swsscommon.has_entry('SFLOW_COLLECTOR', 'flow-collector') is True
    else:
        assert fake_swsscommon.writes == [('set_entry', 'SFLOW_COLLECTOR', 'flow-collector', None)]
        assert fake_swsscommon.has_entry('SFLOW_COLLECTOR', 'flow-collector') is False


def test_absent_idempotent(fake_swsscommon, run_module):
    result = run_module(sflow_collector, dict(name='flow-collector', state='absent'))
    assert result['changed'] is False
    assert result['diff'] == {'before': {}, 'after': {}}
    assert fake_swsscommon.writes == []


def test_present_requires_address(fake_swsscommon, run_module):
    result = run_module(sflow_collector, dict(name='flow-collector'), expect_failure=True)
    assert 'state is present but all of the following are missing: address' in result['msg']


def test_invalid_address(fake_swsscommon, run_module):
    result = run_module(sflow_collector, dict(name='flow-collector', address='collector.example.com'), expect_failure=True)
    assert result['msg'] == 'collector address "collector.example.com" is not a valid IP address'
    assert fake_swsscommon.writes == []


@pytest.mark.parametrize('port', (-1, 65536))
def test_invalid_port(fake_swsscommon, run_module, port):
    result = run_module(sflow_collector, dict(name='flow-collector', address='192.0.2.1', port=port), expect_failure=True)
    assert result['msg'] == 'port must be between 0 and 65535, got %d' % port
    assert fake_swsscommon.writes == []


def test_name_too_long(fake_swsscommon, run_module):
    name = 'a' * 17
    result = run_module(sflow_collector, dict(name=name, address='192.0.2.1'), expect_failure=True)
    assert result['msg'] == 'collector name "%s" must be between 1 and 16 characters' % name
    assert fake_swsscommon.writes == []


def test_at_most_two_collectors(fake_swsscommon, run_module):
    fake_swsscommon.seed({'SFLOW_COLLECTOR': {
        'one': {'collector_ip': '192.0.2.1', 'collector_port': '6343', 'collector_vrf': 'default'},
        'two': {'collector_ip': '192.0.2.2', 'collector_port': '6343', 'collector_vrf': 'default'},
    }})
    result = run_module(sflow_collector, dict(name='three', address='192.0.2.3'), expect_failure=True)
    assert result['msg'] == 'only 2 sFlow collectors can be configured, found: one, two'
    assert fake_swsscommon.writes == []
    # Updating or removing one of the existing collectors is still allowed
    result = run_module(sflow_collector, dict(name='two', address='192.0.2.22'))
    assert result['changed'] is True
    result = run_module(sflow_collector, dict(name='one', state='absent'))
    assert result['changed'] is True
