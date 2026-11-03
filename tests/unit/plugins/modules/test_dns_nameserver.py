# -*- coding: utf-8 -*-
#
# GNU General Public License v3.0+ (see https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import (absolute_import, division, print_function)
__metaclass__ = type

import pytest

from ansible_collections.community.sonic.plugins.modules import dns_nameserver

TABLE = 'DNS_NAMESERVER'
V6 = '2001:db8::53'
V4 = '192.0.2.53'


def seed(fake_swsscommon, *keys):
    fake_swsscommon.seed({TABLE: dict((key, {}) for key in keys)})


def table(*keys):
    return dict((key, {}) for key in keys)


# -- pure helpers ---------------------------------------------------------------

def test_validate_addresses_canonicalises_and_dedupes():
    assert dns_nameserver.validate_addresses([' 2001:DB8:0::53 ', '192.0.2.53', '2001:db8::53']) == [V6, V4]


@pytest.mark.parametrize('bad', ('falafel', '192.0.2.0/24', '2001:db8::53/128', '', '192.0.2.256'))
def test_validate_addresses_rejects_non_addresses(bad):
    with pytest.raises(ValueError) as excinfo:
        dns_nameserver.validate_addresses([V4, bad])
    assert 'is not a valid IPv4 or IPv6 address' in str(excinfo.value)
    assert bad in str(excinfo.value)


def test_plan_present_adds_missing_only():
    assert dns_nameserver.plan_nameservers([V6], [V6, V4], 'present', False) == ([V4], [], [V6, V4])


def test_plan_present_exclusive_removes_others():
    to_add, to_remove, after = dns_nameserver.plan_nameservers(['10.0.0.1', V6], [V6, V4], 'present', True)
    assert to_add == [V4]
    assert to_remove == ['10.0.0.1']
    assert after == [V6, V4]


def test_plan_absent_removes_present_only():
    assert dns_nameserver.plan_nameservers([V6, V4], [V4, '10.0.0.1'], 'absent', False) == ([], [V4], [V6])


def test_plan_matches_stored_keys_by_canonical_form():
    stored = '2001:DB8:0:0:0:0:0:53'
    assert dns_nameserver.plan_nameservers([stored], [V6], 'present', False) == ([], [], [stored])
    assert dns_nameserver.plan_nameservers([stored], [V6], 'absent', False) == ([], [stored], [])
    assert dns_nameserver.plan_nameservers([stored, 'garbage'], [V6], 'present', True) == ([], ['garbage'], [stored])


# -- module runs ------------------------------------------------------------------

@pytest.mark.parametrize('check_mode', (True, False))
def test_add_address(fake_swsscommon, run_module, check_mode):
    seed(fake_swsscommon, V4)
    result = run_module(dns_nameserver, dict(address=V6), check_mode=check_mode)
    assert result['changed'] is True
    assert result['diff'] == {'before': table(V4), 'after': table(V4, V6)}
    assert result['servers'] == [V4, V6]
    if check_mode:
        assert fake_swsscommon.writes == []
        assert not fake_swsscommon.has_entry(TABLE, V6)
    else:
        assert fake_swsscommon.writes == [('set_entry', TABLE, V6, {})]
        assert fake_swsscommon.has_entry(TABLE, V6)
        assert fake_swsscommon.get_entry(TABLE, V6) == {}


@pytest.mark.parametrize('check_mode', (True, False))
def test_add_address_idempotent(fake_swsscommon, run_module, check_mode):
    seed(fake_swsscommon, V6)
    result = run_module(dns_nameserver, dict(address='2001:DB8::53'), check_mode=check_mode)
    assert result['changed'] is False
    assert result['diff'] == {'before': table(V6), 'after': table(V6)}
    assert result['servers'] == [V6]
    assert fake_swsscommon.writes == []


@pytest.mark.parametrize('check_mode', (True, False))
def test_remove_address(fake_swsscommon, run_module, check_mode):
    seed(fake_swsscommon, V6, V4)
    result = run_module(dns_nameserver, dict(address=V4, state='absent'), check_mode=check_mode)
    assert result['changed'] is True
    assert result['diff'] == {'before': table(V6, V4), 'after': table(V6)}
    assert result['servers'] == [V6]
    if check_mode:
        assert fake_swsscommon.writes == []
        assert fake_swsscommon.has_entry(TABLE, V4)
    else:
        assert fake_swsscommon.writes == [('set_entry', TABLE, V4, None)]
        assert not fake_swsscommon.has_entry(TABLE, V4)
        assert fake_swsscommon.has_entry(TABLE, V6)


def test_remove_absent_address_is_noop(fake_swsscommon, run_module):
    result = run_module(dns_nameserver, dict(address=V4, state='absent'))
    assert result['changed'] is False
    assert result['diff'] == {'before': {}, 'after': {}}
    assert result['servers'] == []
    assert fake_swsscommon.writes == []


@pytest.mark.parametrize('check_mode', (True, False))
def test_servers_merge(fake_swsscommon, run_module, check_mode):
    seed(fake_swsscommon, '10.0.0.1', V6)
    result = run_module(dns_nameserver, dict(servers=[V6, V4]), check_mode=check_mode)
    assert result['changed'] is True
    assert result['diff'] == {'before': table('10.0.0.1', V6), 'after': table('10.0.0.1', V6, V4)}
    assert result['servers'] == ['10.0.0.1', V6, V4]
    if check_mode:
        assert fake_swsscommon.writes == []
    else:
        assert fake_swsscommon.writes == [('set_entry', TABLE, V4, {})]
        assert sorted(fake_swsscommon.get_table(TABLE)) == sorted(['10.0.0.1', V6, V4])


@pytest.mark.parametrize('check_mode', (True, False))
def test_servers_exclusive(fake_swsscommon, run_module, check_mode):
    seed(fake_swsscommon, '10.0.0.1', V6)
    result = run_module(dns_nameserver, dict(servers=[V6, V4], exclusive=True), check_mode=check_mode)
    assert result['changed'] is True
    assert result['diff'] == {'before': table('10.0.0.1', V6), 'after': table(V6, V4)}
    assert result['servers'] == [V6, V4]
    if check_mode:
        assert fake_swsscommon.writes == []
        assert sorted(fake_swsscommon.get_table(TABLE)) == sorted(['10.0.0.1', V6])
    else:
        assert fake_swsscommon.writes == [('set_entry', TABLE, '10.0.0.1', None), ('set_entry', TABLE, V4, {})]
        assert fake_swsscommon.get_table(TABLE) == table(V6, V4)


def test_servers_exclusive_idempotent(fake_swsscommon, run_module):
    seed(fake_swsscommon, V6, V4)
    result = run_module(dns_nameserver, dict(servers=[V4, V6], exclusive=True))
    assert result['changed'] is False
    assert result['diff'] == {'before': table(V6, V4), 'after': table(V6, V4)}
    assert fake_swsscommon.writes == []


def test_servers_exclusive_empty_clears_table(fake_swsscommon, run_module):
    seed(fake_swsscommon, V6, V4)
    result = run_module(dns_nameserver, dict(servers=[], exclusive=True))
    assert result['changed'] is True
    assert result['diff'] == {'before': table(V6, V4), 'after': {}}
    assert result['servers'] == []
    assert fake_swsscommon.get_table(TABLE) == {}


def test_servers_absent(fake_swsscommon, run_module):
    seed(fake_swsscommon, V6, V4)
    result = run_module(dns_nameserver, dict(servers=[V4, '10.0.0.1'], state='absent'))
    assert result['changed'] is True
    assert result['diff'] == {'before': table(V6, V4), 'after': table(V6)}
    assert fake_swsscommon.writes == [('set_entry', TABLE, V4, None)]


def test_too_many_nameservers_fails_before_writing(fake_swsscommon, run_module):
    seed(fake_swsscommon, '10.0.0.1', '10.0.0.2')
    result = run_module(dns_nameserver, dict(servers=[V6, V4]), expect_failure=True)
    assert 'at most 3 DNS nameservers' in result['msg']
    assert '4 would be configured' in result['msg']
    assert fake_swsscommon.writes == []

    # Replacing the list keeps it within the limit.
    result = run_module(dns_nameserver, dict(servers=['10.0.0.1', V6, V4], exclusive=True))
    assert result['changed'] is True
    assert result['servers'] == ['10.0.0.1', V6, V4]


def test_too_many_nameservers_in_one_call(fake_swsscommon, run_module):
    result = run_module(dns_nameserver, dict(servers=['10.0.0.1', '10.0.0.2', '10.0.0.3', V4]), expect_failure=True)
    assert 'at most 3 DNS nameservers' in result['msg']
    assert fake_swsscommon.writes == []


@pytest.mark.parametrize('params', (dict(address='falafel'), dict(servers=[V4, '192.0.2.0/24'])))
def test_invalid_address_fails(fake_swsscommon, run_module, params):
    result = run_module(dns_nameserver, params, expect_failure=True)
    assert 'is not a valid IPv4 or IPv6 address' in result['msg']
    assert fake_swsscommon.writes == []


def test_address_and_servers_are_mutually_exclusive(fake_swsscommon, run_module):
    result = run_module(dns_nameserver, dict(address=V4, servers=[V6]), expect_failure=True)
    assert 'mutually exclusive' in result['msg']


def test_one_of_address_or_servers_is_required(fake_swsscommon, run_module):
    result = run_module(dns_nameserver, dict(state='absent'), expect_failure=True)
    assert 'one of the following is required' in result['msg']


def test_exclusive_requires_servers(fake_swsscommon, run_module):
    result = run_module(dns_nameserver, dict(address=V4, exclusive=True), expect_failure=True)
    assert 'servers' in result['msg']


def test_exclusive_with_absent_fails(fake_swsscommon, run_module):
    seed(fake_swsscommon, V6)
    result = run_module(dns_nameserver, dict(servers=[V6], exclusive=True, state='absent'), expect_failure=True)
    assert 'exclusive=true cannot be combined with state=absent' in result['msg']
    assert fake_swsscommon.writes == []

