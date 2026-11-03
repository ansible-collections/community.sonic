# -*- coding: utf-8 -*-
#
# GNU General Public License v3.0+ (see https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import (absolute_import, division, print_function)
__metaclass__ = type

import pytest

from ansible_collections.community.sonic.plugins.modules import telemetry_client


TABLE = 'TELEMETRY_CLIENT'

GROUPS = [dict(name='collectors', collectors=['[2001:db8::20]:8080', '[2001:db8::21]:8080'])]
SUBSCRIPTIONS = [
    dict(name='port_counters', destination_group='collectors', path_target='COUNTERS_DB',
         paths=['COUNTERS/Ethernet*'], report_type='periodic', report_interval=10000),
    dict(name='transceiver_dom', destination_group='collectors', path_target='STATE_DB',
         paths=['TRANSCEIVER_DOM_SENSOR'], report_type='periodic', report_interval=60000),
]
PARAMS = dict(encoding='JSON_IETF', retry_interval=30, unidirectional=True,
              destination_groups=GROUPS, subscriptions=SUBSCRIPTIONS)

EXPECTED = {
    'Global': {'encoding': 'JSON_IETF', 'retry_interval': '30', 'unidirectional': 'true'},
    'DestinationGroup_collectors': {'dst_addr': '[2001:db8::20]:8080,[2001:db8::21]:8080'},
    'Subscription_port_counters': {
        'dst_group': 'collectors', 'path_target': 'COUNTERS_DB', 'paths': 'COUNTERS/Ethernet*',
        'report_type': 'periodic', 'report_interval': '10000'},
    'Subscription_transceiver_dom': {
        'dst_group': 'collectors', 'path_target': 'STATE_DB', 'paths': 'TRANSCEIVER_DOM_SENSOR',
        'report_type': 'periodic', 'report_interval': '60000'},
}


# -- pure logic ------------------------------------------------------------------

def test_build_group_entry():
    assert telemetry_client.build_group_entry('g', ['192.0.2.1:8080', ' 192.0.2.1:8080 ', 'host.example:1']) == {
        'dst_addr': '192.0.2.1:8080,host.example:1'}
    with pytest.raises(telemetry_client.TelemetryClientError, match='at least one collector'):
        telemetry_client.build_group_entry('g', [])
    for bad in ('192.0.2.1', '192.0.2.1:0', '192.0.2.1:70000', '2001:db8::1:8080', 'a,b:1', 'a b:1'):
        with pytest.raises(telemetry_client.TelemetryClientError, match='must be host:port'):
            telemetry_client.build_group_entry('g', [bad])


def test_build_subscription_entry():
    assert telemetry_client.build_subscription_entry('s', 'g', ['A', ' B ', 'A'], known_groups={'g'}) == {
        'dst_group': 'g', 'paths': 'A,B'}
    with pytest.raises(telemetry_client.TelemetryClientError, match='not configured'):
        telemetry_client.build_subscription_entry('s', 'nope', ['A'], known_groups={'g'})
    with pytest.raises(telemetry_client.TelemetryClientError, match='at least one path'):
        telemetry_client.build_subscription_entry('s', 'g', [], known_groups={'g'})
    with pytest.raises(telemetry_client.TelemetryClientError, match='path "A,B" is invalid'):
        telemetry_client.build_subscription_entry('s', 'g', ['A,B'], known_groups={'g'})
    with pytest.raises(telemetry_client.TelemetryClientError, match='report_interval must be positive'):
        telemetry_client.build_subscription_entry('s', 'g', ['A'], report_interval=0, known_groups={'g'})


def test_plan_table_exclusive_replaces_everything():
    current = {'Global': {'src_ip': '192.0.2.9'}, 'DestinationGroup_old': {'dst_addr': '192.0.2.1:1'},
               'Subscription_old': {'dst_group': 'old', 'paths': 'X'}}
    after = telemetry_client.plan_table(current, {'retry_interval': 30}, GROUPS, SUBSCRIPTIONS, exclusive=True)
    assert after == dict(EXPECTED, Global={'retry_interval': '30'})


def test_plan_table_merge_keeps_other_entries():
    current = {'Global': {'src_ip': '192.0.2.9', 'retry_interval': '5'}, 'DestinationGroup_old': {'dst_addr': '192.0.2.1:1'},
               'Subscription_old': {'dst_group': 'old', 'paths': 'X'}}
    new_sub = [dict(name='lldp', destination_group='old', paths=['LLDP_ENTRY_TABLE'], report_type='stream')]
    after = telemetry_client.plan_table(current, {'retry_interval': 30}, [], new_sub, exclusive=False)
    assert after == {
        'Global': {'src_ip': '192.0.2.9', 'retry_interval': '30'},
        'DestinationGroup_old': {'dst_addr': '192.0.2.1:1'},
        'Subscription_old': {'dst_group': 'old', 'paths': 'X'},
        'Subscription_lldp': {'dst_group': 'old', 'paths': 'LLDP_ENTRY_TABLE', 'report_type': 'stream'},
    }


def test_plan_table_rejects_bad_names_and_duplicates():
    with pytest.raises(telemetry_client.TelemetryClientError, match='destination group name "a|b" is invalid'):
        telemetry_client.plan_table({}, {}, [dict(name='a|b', collectors=['h:1'])], [], True)
    with pytest.raises(telemetry_client.TelemetryClientError, match='destination group "g" is listed twice'):
        telemetry_client.plan_table({}, {}, [dict(name='g', collectors=['h:1']), dict(name='g', collectors=['h:2'])], [], True)
    with pytest.raises(telemetry_client.TelemetryClientError, match='subscription "s" is listed twice'):
        telemetry_client.plan_table({}, {}, [dict(name='g', collectors=['h:1'])],
                                    [dict(name='s', destination_group='g', paths=['A']),
                                     dict(name='s', destination_group='g', paths=['B'])], True)


# -- module runs ------------------------------------------------------------------

@pytest.mark.parametrize('check_mode', (True, False))
def test_create(fake_swsscommon, run_module, check_mode):
    result = run_module(telemetry_client, PARAMS, check_mode=check_mode)
    assert result['changed'] is True
    assert result['destination_groups'] == ['collectors']
    assert result['subscriptions'] == ['port_counters', 'transceiver_dom']
    assert result['diff'] == {'before': {}, 'after': EXPECTED}
    if check_mode:
        assert fake_swsscommon.writes == []
        assert fake_swsscommon.get_table(TABLE) == {}
    else:
        assert fake_swsscommon.writes == [('set_entry', TABLE, key, EXPECTED[key]) for key in sorted(EXPECTED)]
        assert fake_swsscommon.get_table(TABLE) == EXPECTED
        # Comma lists are plain strings, not field@ lists.
        assert fake_swsscommon.store[TABLE]['DestinationGroup_collectors'] == {
            'dst_addr': '[2001:db8::20]:8080,[2001:db8::21]:8080'}


@pytest.mark.parametrize('check_mode', (True, False))
def test_idempotent(fake_swsscommon, run_module, check_mode):
    fake_swsscommon.seed({TABLE: EXPECTED})
    result = run_module(telemetry_client, PARAMS, check_mode=check_mode)
    assert result['changed'] is False
    assert result['diff'] == {'before': EXPECTED, 'after': EXPECTED}
    assert fake_swsscommon.writes == []


@pytest.mark.parametrize('check_mode', (True, False))
def test_exclusive_update_removes_unlisted(fake_swsscommon, run_module, check_mode):
    extra = {'DestinationGroup_old': {'dst_addr': '192.0.2.1:1'}, 'Subscription_old': {'dst_group': 'old', 'paths': 'X'}}
    fake_swsscommon.seed({TABLE: dict(EXPECTED, **extra)})
    params = dict(PARAMS, retry_interval=60, subscriptions=SUBSCRIPTIONS[:1])
    result = run_module(telemetry_client, params, check_mode=check_mode)
    after = {k: v for k, v in EXPECTED.items() if k != 'Subscription_transceiver_dom'}
    after['Global'] = dict(EXPECTED['Global'], retry_interval='60')
    assert result['changed'] is True
    assert result['diff']['after'] == after
    assert result['subscriptions'] == ['port_counters']
    if check_mode:
        assert fake_swsscommon.writes == []
    else:
        assert fake_swsscommon.writes == [
            ('set_entry', TABLE, 'DestinationGroup_old', None),
            ('set_entry', TABLE, 'Subscription_old', None),
            ('set_entry', TABLE, 'Subscription_transceiver_dom', None),
            ('set_entry', TABLE, 'Global', after['Global']),
        ]
        assert fake_swsscommon.get_table(TABLE) == after


@pytest.mark.parametrize('check_mode', (True, False))
def test_non_exclusive_merge(fake_swsscommon, run_module, check_mode):
    fake_swsscommon.seed({TABLE: EXPECTED})
    params = dict(exclusive=False, src_ip='192.0.2.9', subscriptions=[
        dict(name='lldp', destination_group='collectors', path_target='APPL_DB', paths=['LLDP_ENTRY_TABLE'],
             report_type='stream')])
    result = run_module(telemetry_client, params, check_mode=check_mode)
    lldp = {'dst_group': 'collectors', 'path_target': 'APPL_DB', 'paths': 'LLDP_ENTRY_TABLE', 'report_type': 'stream'}
    after = dict(EXPECTED, Global=dict(EXPECTED['Global'], src_ip='192.0.2.9'), Subscription_lldp=lldp)
    assert result['changed'] is True
    assert result['diff'] == {'before': EXPECTED, 'after': after}
    assert result['subscriptions'] == ['lldp', 'port_counters', 'transceiver_dom']
    if check_mode:
        assert fake_swsscommon.writes == []
        assert fake_swsscommon.get_table(TABLE) == EXPECTED
    else:
        assert fake_swsscommon.writes == [
            ('set_entry', TABLE, 'Global', after['Global']),
            ('set_entry', TABLE, 'Subscription_lldp', after['Subscription_lldp']),
        ]
        assert fake_swsscommon.get_table(TABLE) == after


def test_non_exclusive_without_options_is_not_a_change(fake_swsscommon, run_module):
    fake_swsscommon.seed({TABLE: EXPECTED})
    result = run_module(telemetry_client, dict(exclusive=False))
    assert result['changed'] is False
    assert fake_swsscommon.writes == []


@pytest.mark.parametrize('check_mode', (True, False))
def test_absent(fake_swsscommon, run_module, check_mode):
    fake_swsscommon.seed({TABLE: EXPECTED})
    result = run_module(telemetry_client, dict(state='absent'), check_mode=check_mode)
    assert result['changed'] is True
    assert result['diff'] == {'before': EXPECTED, 'after': {}}
    assert result['destination_groups'] == []
    assert result['subscriptions'] == []
    if check_mode:
        assert fake_swsscommon.writes == []
        assert fake_swsscommon.get_table(TABLE) == EXPECTED
    else:
        assert fake_swsscommon.writes == [('set_entry', TABLE, key, None) for key in sorted(EXPECTED)]
        assert fake_swsscommon.get_table(TABLE) == {}


def test_absent_when_empty_is_not_a_change(fake_swsscommon, run_module):
    result = run_module(telemetry_client, dict(state='absent'))
    assert result['changed'] is False
    assert fake_swsscommon.writes == []


@pytest.mark.parametrize('params,msg', (
    (dict(retry_interval=-1), 'retry_interval must not be negative, got -1'),
    (dict(src_ip='not-an-ip'), 'src_ip "not-an-ip" is not a valid IPv4 or IPv6 address'),
    (dict(destination_groups=[dict(name='g', collectors=['192.0.2.1'])]),
     'destination group "g": collector "192.0.2.1" must be host:port or [ipv6]:port'),
    (dict(destination_groups=[dict(name='bad name', collectors=['192.0.2.1:1'])]),
     'destination group name "bad name" is invalid; use letters, digits, "_", "-" and "." only'),
    (dict(subscriptions=[dict(name='s', destination_group='missing', paths=['A'])]),
     'subscription "s" refers to destination group "missing", which is not configured'),
    (dict(destination_groups=[dict(name='g', collectors=['h:1'])],
          subscriptions=[dict(name='s', destination_group='g', paths=['A'], report_interval=0)]),
     'subscription "s": report_interval must be positive, got 0'),
))
def test_invalid_values_fail(fake_swsscommon, run_module, params, msg):
    fake_swsscommon.seed({TABLE: EXPECTED})
    result = run_module(telemetry_client, params, expect_failure=True)
    assert result['msg'] == msg
    assert fake_swsscommon.writes == []
    assert fake_swsscommon.get_table(TABLE) == EXPECTED


def test_argument_spec_validates_suboptions(fake_swsscommon, run_module):
    result = run_module(telemetry_client, dict(subscriptions=[dict(name='s', destination_group='g', paths=['A'],
                                                                   report_type='sometimes')]), expect_failure=True)
    assert 'report_type' in result['msg']
    result = run_module(telemetry_client, dict(destination_groups=[dict(name='g')]), expect_failure=True)
    assert 'collectors' in result['msg']
    assert fake_swsscommon.writes == []


def test_non_exclusive_subscription_may_use_existing_group(fake_swsscommon, run_module):
    fake_swsscommon.seed({TABLE: {'DestinationGroup_existing': {'dst_addr': '192.0.2.1:1'}}})
    result = run_module(telemetry_client, dict(exclusive=False, subscriptions=[
        dict(name='s', destination_group='existing', paths=['A'])]))
    assert result['changed'] is True
    assert fake_swsscommon.get_entry(TABLE, 'Subscription_s') == {'dst_group': 'existing', 'paths': 'A'}

    # ... but not when the table is replaced exclusively.
    result = run_module(telemetry_client, dict(subscriptions=[dict(name='s', destination_group='existing', paths=['A'])]),
                        expect_failure=True)
    assert result['msg'] == 'subscription "s" refers to destination group "existing", which is not configured'
