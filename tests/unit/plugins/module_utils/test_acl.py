# -*- coding: utf-8 -*-
#
# GNU General Public License v3.0+ (see https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import (absolute_import, division, print_function)
__metaclass__ = type

import pytest

from ansible_collections.community.sonic.plugins.module_utils import acl
from ansible_collections.community.sonic.plugins.module_utils.config_db import ConfigDB
from ansible_collections.community.sonic.tests.unit.fake_swsscommon import FakeSwssCommon


class FakeClock(object):
    """Replacement for ``acl.monotonic``/``acl.sleep`` that advances on sleep and can run a callback."""

    def __init__(self, on_sleep=None):
        self.now = 0.0
        self.sleeps = []
        self.on_sleep = on_sleep

    def monotonic(self):
        return self.now

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.now += seconds
        if self.on_sleep:
            self.on_sleep(self)


@pytest.fixture
def clock(monkeypatch):
    fake = FakeClock()
    monkeypatch.setattr(acl, 'monotonic', fake.monotonic)
    monkeypatch.setattr(acl, 'sleep', fake.sleep)
    return fake


def state_db(seed=None):
    fake = FakeSwssCommon(seed)
    return ConfigDB(None, db_name='STATE_DB', connector=fake.ConfigDBConnector()).connect(), fake


# -- layout -----------------------------------------------------------------------

@pytest.mark.parametrize('acl_tables,expected', (
    ({}, (None, {})),
    ({'X': {'type': 'L3V4V6'}}, ('combined', {'X': 'L3V4V6'})),
    ({'X': {'type': 'L3'}, 'X_v6': {'type': 'L3V6'}}, ('split', {'X': 'L3', 'X_v6': 'L3V6'})),
    ({'X': {'type': 'L3'}}, ('split', {'X': 'L3'})),
    ({'X': {'type': 'L3'}, 'X_v6': {'type': 'MIRROR'}}, ('split', {'X': 'L3'})),
    ({'X_v6': {'type': 'L3V6'}}, ('split', {'X_v6': 'L3V6'})),
    ({'X': {'type': 'MIRROR'}}, (None, {'X': 'MIRROR'})),
    ({'X': {'type': 'L3V6'}}, (None, {'X': 'L3V6'})),
))
def test_layout_from_config(acl_tables, expected):
    assert acl.layout_from_config('X', acl_tables) == expected


def test_layout_from_config_custom_suffix():
    tables = {'X': {'type': 'L3'}, 'X-ipv6': {'type': 'L3V6'}, 'X_v6': {'type': 'L3V6'}}
    assert acl.layout_from_config('X', tables, suffix='-ipv6') == ('split', {'X': 'L3', 'X-ipv6': 'L3V6'})


def test_tables_for_mode():
    assert acl.tables_for_mode('X', 'combined') == {'X': 'L3V4V6'}
    assert list(acl.tables_for_mode('X', 'split').items()) == [('X', 'L3'), ('X_v6', 'L3V6')]
    assert acl.tables_for_mode('X', 'split', suffix='6') == {'X': 'L3', 'X6': 'L3V6'}
    with pytest.raises(acl.AclError):
        acl.tables_for_mode('X', 'auto')


def test_list_field():
    assert acl.list_field({'ports': ['']}, 'ports') == []
    assert acl.list_field({'ports': ['Ethernet0', 'Ethernet4']}, 'ports') == ['Ethernet0', 'Ethernet4']
    assert acl.list_field({}, 'ports') == []


@pytest.mark.parametrize('entry,expected', (
    ({'action_list': 'PACKET_ACTION', 'supported_L3V4V6': 'true'}, True),
    ({'action_list': 'PACKET_ACTION', 'supported_L3V4V6': 'false'}, False),
    ({'action_list': 'PACKET_ACTION'}, None),
    (None, None),
))
def test_capability_l3v4v6(entry, expected):
    db, _fake = state_db({'ACL_STAGE_CAPABILITY_TABLE': {'INGRESS': entry}} if entry else {})
    assert acl.capability_l3v4v6(db, 'ingress') is expected
    assert acl.capability_l3v4v6(db, 'egress') is None


# -- status -----------------------------------------------------------------------

def test_wait_for_status_active_immediately(clock):
    db, _fake = state_db({'ACL_TABLE_TABLE': {'X': {'status': 'Active'}, 'X_v6': {'status': 'Active'}}})
    assert acl.wait_for_status(db, 'ACL_TABLE_TABLE', ['X', 'X_v6'], 30) == {'X': 'Active', 'X_v6': 'Active'}
    assert clock.sleeps == []


def test_wait_for_status_becomes_active(clock):
    db, fake = state_db()

    def orchagent(c):
        if c.now >= 1.5:
            fake.seed({'ACL_RULE_TABLE': {'X|R1': {'status': 'Active'}}})
    clock.on_sleep = orchagent

    assert acl.wait_for_status(db, 'ACL_RULE_TABLE', [('X', 'R1')], 30) == {'X|R1': 'Active'}
    assert clock.now == 1.5


def test_wait_for_status_inactive_stops_early(clock):
    db, _fake = state_db({'ACL_TABLE_TABLE': {'X': {'status': 'Inactive'}}})
    assert acl.wait_for_status(db, 'ACL_TABLE_TABLE', ['X', 'Y'], 30) == {'X': 'Inactive', 'Y': None}
    assert clock.sleeps == []


def test_wait_for_status_times_out(clock):
    db, _fake = state_db({'ACL_TABLE_TABLE': {'X': {'status': 'Pending creation'}}})
    assert acl.wait_for_status(db, 'ACL_TABLE_TABLE', ['X'], 2) == {'X': 'Pending creation'}
    assert clock.now == 2
    assert all(s <= 0.5 for s in clock.sleeps)


def test_check_status_messages(clock):
    db, _fake = state_db({'ACL_TABLE_TABLE': {'X': {'status': 'Inactive'}}})
    with pytest.raises(acl.AclStatusError) as excinfo:
        acl.check_status(db, 'ACL_TABLE_TABLE', ['X', 'X_v6'], 5, 'ACL tables X, X_v6')
    assert str(excinfo.value) == (
        'orchagent did not accept ACL tables X, X_v6 (X: Inactive, X_v6: no status reported); '
        'see "show logging" for the reason and STATE_DB ACL_TABLE_TABLE for the status')


def test_check_status_disabled(clock):
    db, _fake = state_db()
    assert acl.check_status(db, 'ACL_TABLE_TABLE', ['X'], 0, 'ACL table X') == {}
    assert acl.check_status(db, 'ACL_TABLE_TABLE', [], 30, 'ACL table X') == {}
