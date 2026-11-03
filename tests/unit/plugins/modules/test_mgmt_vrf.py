# -*- coding: utf-8 -*-
# GNU General Public License v3.0+ (see https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import (absolute_import, division, print_function)
__metaclass__ = type

import pytest

from ansible_collections.community.sonic.plugins.modules import mgmt_vrf

TABLE = 'MGMT_VRF_CONFIG'
KEY = 'vrf_global'


@pytest.mark.parametrize('entry,expected', (
    ({}, False),
    ({'mgmtVrfEnabled': 'false'}, False),
    ({'mgmtVrfEnabled': 'true'}, True),
    ({'mgmtVrfEnabled': 'True'}, True),
    ({'in_band_mgmt_enabled': 'true'}, False),
))
def test_is_mgmt_vrf_enabled(entry, expected):
    assert mgmt_vrf.is_mgmt_vrf_enabled(entry) is expected


@pytest.mark.parametrize('check_mode', (True, False))
@pytest.mark.parametrize('current', (None, {}, {'mgmtVrfEnabled': 'false'}))
def test_enable(fake_swsscommon, run_module, check_mode, current):
    if current is not None:
        fake_swsscommon.seed({TABLE: {KEY: current}})
    result = run_module(mgmt_vrf, dict(enabled=True), check_mode=check_mode)
    assert result['changed'] is True
    assert result['enabled'] is True
    assert result['diff'] == {'before': current or {}, 'after': {'mgmtVrfEnabled': 'true'}}
    if check_mode:
        assert fake_swsscommon.writes == []
        assert fake_swsscommon.get_entry(TABLE, KEY) == (current or {})
    else:
        assert fake_swsscommon.writes == [('mod_entry', TABLE, KEY, {'mgmtVrfEnabled': 'true'})]
        assert fake_swsscommon.get_entry(TABLE, KEY) == {'mgmtVrfEnabled': 'true'}


@pytest.mark.parametrize('check_mode', (True, False))
def test_enable_is_idempotent(fake_swsscommon, run_module, check_mode):
    fake_swsscommon.seed({TABLE: {KEY: {'mgmtVrfEnabled': 'true'}}})
    result = run_module(mgmt_vrf, dict(enabled=True), check_mode=check_mode)
    assert result['changed'] is False
    assert result['enabled'] is True
    assert result['diff'] == {'before': {'mgmtVrfEnabled': 'true'}, 'after': {'mgmtVrfEnabled': 'true'}}
    assert fake_swsscommon.writes == []


@pytest.mark.parametrize('check_mode', (True, False))
def test_disable(fake_swsscommon, run_module, check_mode):
    fake_swsscommon.seed({TABLE: {KEY: {'mgmtVrfEnabled': 'true', 'in_band_mgmt_enabled': 'false'}}})
    result = run_module(mgmt_vrf, dict(enabled=False), check_mode=check_mode)
    assert result['changed'] is True
    assert result['enabled'] is False
    assert result['diff'] == {
        'before': {'mgmtVrfEnabled': 'true', 'in_band_mgmt_enabled': 'false'},
        'after': {'mgmtVrfEnabled': 'false', 'in_band_mgmt_enabled': 'false'},
    }
    if check_mode:
        assert fake_swsscommon.writes == []
    else:
        # Other fields of the entry are kept.
        assert fake_swsscommon.writes == [('mod_entry', TABLE, KEY, {'mgmtVrfEnabled': 'false'})]
        assert fake_swsscommon.get_entry(TABLE, KEY) == {'mgmtVrfEnabled': 'false', 'in_band_mgmt_enabled': 'false'}


@pytest.mark.parametrize('check_mode', (True, False))
@pytest.mark.parametrize('current', (None, {}, {'mgmtVrfEnabled': 'false'}))
def test_disable_is_idempotent_including_missing_entry(fake_swsscommon, run_module, check_mode, current):
    if current is not None:
        fake_swsscommon.seed({TABLE: {KEY: current}})
    result = run_module(mgmt_vrf, dict(enabled=False), check_mode=check_mode)
    assert result['changed'] is False
    assert result['enabled'] is False
    assert result['diff'] == {'before': current or {}, 'after': current or {}}
    assert fake_swsscommon.writes == []
    assert fake_swsscommon.has_entry(TABLE, KEY) is (current is not None)


def test_enabled_is_required(fake_swsscommon, run_module):
    result = run_module(mgmt_vrf, dict(), expect_failure=True)
    assert result['failed'] is True
    assert 'enabled' in result['msg']
    assert fake_swsscommon.writes == []
