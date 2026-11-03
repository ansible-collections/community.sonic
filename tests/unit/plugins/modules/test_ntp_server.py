# -*- coding: utf-8 -*-
#
# GNU General Public License v3.0+ (see https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import (absolute_import, division, print_function)
__metaclass__ = type

import pytest

from ansible_collections.community.sonic.plugins.modules import ntp_server

TABLE = 'NTP_SERVER'
V6 = '2001:db8::123'
V4 = '192.0.2.123'
POOL = 'pool.ntp.org'
FULL = {'association_type': 'server', 'iburst': 'on', 'admin_state': 'enabled', 'version': '4',
        'key': '42', 'trusted': 'yes'}


def seed(fake_swsscommon, entries=None, *keys):
    data = dict((key, {}) for key in keys)
    data.update(entries or {})
    fake_swsscommon.seed({TABLE: data})


def table(*keys):
    return dict((key, {}) for key in keys)


# -- pure helpers ---------------------------------------------------------------

def test_validate_servers_canonicalises_and_dedupes():
    assert ntp_server.validate_servers([' 2001:DB8:0::123 ', V4, '2001:db8::123', 'Pool.NTP.org']) == [V6, V4, 'Pool.NTP.org']


@pytest.mark.parametrize('bad', ('', ' ', 'bad address', '192.0.2.0/24', '2001:db8::123/128', '-pool.ntp.org',
                                 'pool_ntp.org', 'ntp|server', '192.0.2.256.1'))
def test_validate_servers_rejects_garbage(bad):
    with pytest.raises(ValueError) as excinfo:
        ntp_server.validate_servers([V4, bad])
    assert 'is not a valid IPv4 or IPv6 address or host name' in str(excinfo.value)


def test_plan_present_reuses_stored_keys():
    assert ntp_server.plan_servers([V6], [V6, V4], 'present', False) == ([V6, V4], [], [V6, V4])


def test_plan_present_exclusive_removes_others():
    targets, to_remove, after = ntp_server.plan_servers(['10.0.0.1', V6], [V6, V4], 'present', True)
    assert targets == [V6, V4]
    assert to_remove == ['10.0.0.1']
    assert after == [V6, V4]


def test_plan_absent_removes_present_only():
    assert ntp_server.plan_servers([V6, V4], [V4, '10.0.0.1'], 'absent', False) == ([], [V4], [V6])


def test_plan_matches_stored_keys_by_canonical_form():
    stored = '2001:DB8:0:0:0:0:0:123'
    assert ntp_server.plan_servers([stored], [V6], 'present', False) == ([stored], [], [stored])
    assert ntp_server.plan_servers([stored], [V6], 'absent', False) == ([], [stored], [])
    assert ntp_server.plan_servers([stored, 'garbage'], [V6], 'present', True) == ([stored], ['garbage'], [stored])


def test_build_server_entry():
    assert ntp_server.build_server_entry() == {}
    assert ntp_server.build_server_entry(association_type='pool', iburst=False, enabled=False, version=3,
                                         key=42, trusted=True) == {
        'association_type': 'pool', 'iburst': 'off', 'admin_state': 'disabled', 'version': 3, 'key': 42,
        'trusted': 'yes'}
    assert ntp_server.build_server_entry(iburst=True, trusted=False) == {'iburst': 'on', 'trusted': 'no'}


# -- module runs ------------------------------------------------------------------

@pytest.mark.parametrize('check_mode', (True, False))
def test_add_address_without_options(fake_swsscommon, run_module, check_mode):
    # The old-image form: the key with an empty value, as `config ntp add` writes it.
    seed(fake_swsscommon, None, V4)
    result = run_module(ntp_server, dict(address=V6), check_mode=check_mode)
    assert result['changed'] is True
    assert result['diff'] == {'before': table(V4), 'after': table(V4, V6)}
    assert result['servers'] == [V4, V6]
    if check_mode:
        assert fake_swsscommon.writes == []
        assert not fake_swsscommon.has_entry(TABLE, V6)
    else:
        assert fake_swsscommon.writes == [('mod_entry', TABLE, V6, {})]
        assert fake_swsscommon.has_entry(TABLE, V6)
        assert fake_swsscommon.get_entry(TABLE, V6) == {}


@pytest.mark.parametrize('check_mode', (True, False))
def test_add_address_with_options(fake_swsscommon, run_module, check_mode):
    result = run_module(ntp_server, dict(address=V6, iburst=True, enabled=True, association_type='server',
                                         version=4, key=42, trusted=True), check_mode=check_mode)
    assert result['changed'] is True
    assert result['diff'] == {'before': {}, 'after': {V6: FULL}}
    assert result['servers'] == [V6]
    if check_mode:
        assert fake_swsscommon.writes == []
    else:
        assert fake_swsscommon.writes == [('mod_entry', TABLE, V6, FULL)]
        assert fake_swsscommon.get_entry(TABLE, V6) == FULL


@pytest.mark.parametrize('check_mode', (True, False))
def test_add_address_idempotent(fake_swsscommon, run_module, check_mode):
    seed(fake_swsscommon, {V6: FULL})
    result = run_module(ntp_server, dict(address='2001:DB8::123', iburst=True, version=4, trusted=True),
                        check_mode=check_mode)
    assert result['changed'] is False
    assert result['diff'] == {'before': {V6: FULL}, 'after': {V6: FULL}}
    assert result['servers'] == [V6]
    assert fake_swsscommon.writes == []


def test_empty_entry_is_idempotent_without_options(fake_swsscommon, run_module):
    seed(fake_swsscommon, None, V6)
    result = run_module(ntp_server, dict(address=V6))
    assert result['changed'] is False
    assert fake_swsscommon.writes == []


def test_update_only_touches_given_fields(fake_swsscommon, run_module):
    seed(fake_swsscommon, {V6: FULL})
    result = run_module(ntp_server, dict(address=V6, enabled=False, iburst=False))
    assert result['changed'] is True
    after = dict(FULL, admin_state='disabled', iburst='off')
    assert result['diff'] == {'before': {V6: FULL}, 'after': {V6: after}}
    assert fake_swsscommon.writes == [('mod_entry', TABLE, V6, {'admin_state': 'disabled', 'iburst': 'off'})]
    assert fake_swsscommon.get_entry(TABLE, V6) == after


def test_resolve_as_is_left_alone(fake_swsscommon, run_module):
    current = {'resolve_as': V4, 'iburst': 'on'}
    seed(fake_swsscommon, {POOL: current})
    result = run_module(ntp_server, dict(address=POOL, association_type='pool'))
    assert result['changed'] is True
    assert result['diff']['after'][POOL] == dict(current, association_type='pool')
    assert fake_swsscommon.writes == [('mod_entry', TABLE, POOL, {'association_type': 'pool'})]
    assert fake_swsscommon.get_entry(TABLE, POOL)['resolve_as'] == V4


@pytest.mark.parametrize('check_mode', (True, False))
def test_remove_address(fake_swsscommon, run_module, check_mode):
    seed(fake_swsscommon, {V6: FULL}, V4)
    result = run_module(ntp_server, dict(address=V4, state='absent'), check_mode=check_mode)
    assert result['changed'] is True
    assert result['diff'] == {'before': {V6: FULL, V4: {}}, 'after': {V6: FULL}}
    assert result['servers'] == [V6]
    if check_mode:
        assert fake_swsscommon.writes == []
        assert fake_swsscommon.has_entry(TABLE, V4)
    else:
        assert fake_swsscommon.writes == [('set_entry', TABLE, V4, None)]
        assert not fake_swsscommon.has_entry(TABLE, V4)
        assert fake_swsscommon.has_entry(TABLE, V6)


def test_remove_absent_address_is_noop(fake_swsscommon, run_module):
    result = run_module(ntp_server, dict(address=V4, state='absent'))
    assert result['changed'] is False
    assert result['diff'] == {'before': {}, 'after': {}}
    assert result['servers'] == []
    assert fake_swsscommon.writes == []


@pytest.mark.parametrize('check_mode', (True, False))
def test_servers_merge(fake_swsscommon, run_module, check_mode):
    seed(fake_swsscommon, None, '10.0.0.1', V6)
    result = run_module(ntp_server, dict(servers=[V6, V4], iburst=True), check_mode=check_mode)
    assert result['changed'] is True
    assert result['diff'] == {'before': table('10.0.0.1', V6),
                              'after': {'10.0.0.1': {}, V6: {'iburst': 'on'}, V4: {'iburst': 'on'}}}
    assert result['servers'] == ['10.0.0.1', V6, V4]
    if check_mode:
        assert fake_swsscommon.writes == []
        assert fake_swsscommon.get_table(TABLE) == table('10.0.0.1', V6)
    else:
        assert fake_swsscommon.writes == [('mod_entry', TABLE, V6, {'iburst': 'on'}),
                                          ('mod_entry', TABLE, V4, {'iburst': 'on'})]
        assert fake_swsscommon.get_table(TABLE) == {'10.0.0.1': {}, V6: {'iburst': 'on'}, V4: {'iburst': 'on'}}


@pytest.mark.parametrize('check_mode', (True, False))
def test_servers_exclusive(fake_swsscommon, run_module, check_mode):
    seed(fake_swsscommon, None, '10.0.0.1', V6)
    result = run_module(ntp_server, dict(servers=[V6, V4], exclusive=True), check_mode=check_mode)
    assert result['changed'] is True
    assert result['diff'] == {'before': table('10.0.0.1', V6), 'after': table(V6, V4)}
    assert result['servers'] == [V6, V4]
    if check_mode:
        assert fake_swsscommon.writes == []
        assert fake_swsscommon.get_table(TABLE) == table('10.0.0.1', V6)
    else:
        assert fake_swsscommon.writes == [('set_entry', TABLE, '10.0.0.1', None), ('mod_entry', TABLE, V4, {})]
        assert fake_swsscommon.get_table(TABLE) == table(V6, V4)


def test_servers_exclusive_idempotent(fake_swsscommon, run_module):
    seed(fake_swsscommon, {V6: FULL, V4: {'iburst': 'on'}})
    result = run_module(ntp_server, dict(servers=[V4, V6], iburst=True, exclusive=True))
    assert result['changed'] is False
    assert result['diff'] == {'before': {V6: FULL, V4: {'iburst': 'on'}}, 'after': {V6: FULL, V4: {'iburst': 'on'}}}
    assert fake_swsscommon.writes == []


def test_servers_exclusive_empty_clears_table(fake_swsscommon, run_module):
    seed(fake_swsscommon, {V6: FULL}, V4)
    result = run_module(ntp_server, dict(servers=[], exclusive=True))
    assert result['changed'] is True
    assert result['diff'] == {'before': {V6: FULL, V4: {}}, 'after': {}}
    assert result['servers'] == []
    assert fake_swsscommon.get_table(TABLE) == {}


def test_servers_absent(fake_swsscommon, run_module):
    seed(fake_swsscommon, None, V6, V4)
    result = run_module(ntp_server, dict(servers=[V4, '10.0.0.1'], state='absent'))
    assert result['changed'] is True
    assert result['diff'] == {'before': table(V6, V4), 'after': table(V6)}
    assert fake_swsscommon.writes == [('set_entry', TABLE, V4, None)]


def test_pool_by_name(fake_swsscommon, run_module):
    result = run_module(ntp_server, dict(address=POOL, association_type='pool', iburst=True))
    assert result['changed'] is True
    assert result['servers'] == [POOL]
    assert fake_swsscommon.get_entry(TABLE, POOL) == {'association_type': 'pool', 'iburst': 'on'}


@pytest.mark.parametrize('params', (dict(address='bad address'), dict(servers=[V4, '192.0.2.0/24'])))
def test_invalid_address_fails(fake_swsscommon, run_module, params):
    result = run_module(ntp_server, params, expect_failure=True)
    assert 'is not a valid IPv4 or IPv6 address or host name' in result['msg']
    assert fake_swsscommon.writes == []


@pytest.mark.parametrize('key', (0, 65536, -1))
def test_invalid_key_fails(fake_swsscommon, run_module, key):
    result = run_module(ntp_server, dict(address=V4, key=key), expect_failure=True)
    assert 'key must be between 1 and 65535' in result['msg']
    assert fake_swsscommon.writes == []


def test_invalid_version_fails(fake_swsscommon, run_module):
    result = run_module(ntp_server, dict(address=V4, version=2), expect_failure=True)
    assert 'version' in result['msg']
    assert fake_swsscommon.writes == []


def test_address_and_servers_are_mutually_exclusive(fake_swsscommon, run_module):
    result = run_module(ntp_server, dict(address=V4, servers=[V6]), expect_failure=True)
    assert 'mutually exclusive' in result['msg']


def test_one_of_address_or_servers_is_required(fake_swsscommon, run_module):
    result = run_module(ntp_server, dict(state='absent'), expect_failure=True)
    assert 'one of the following is required' in result['msg']


def test_exclusive_requires_servers(fake_swsscommon, run_module):
    result = run_module(ntp_server, dict(address=V4, exclusive=True), expect_failure=True)
    assert 'servers' in result['msg']


def test_exclusive_with_absent_fails(fake_swsscommon, run_module):
    seed(fake_swsscommon, None, V6)
    result = run_module(ntp_server, dict(servers=[V6], exclusive=True, state='absent'), expect_failure=True)
    assert 'exclusive=true cannot be combined with state=absent' in result['msg']
    assert fake_swsscommon.writes == []
