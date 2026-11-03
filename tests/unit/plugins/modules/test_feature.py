# -*- coding: utf-8 -*-
#
# GNU General Public License v3.0+ (see https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import (absolute_import, division, print_function)
__metaclass__ = type

import pytest

from ansible_collections.community.sonic.plugins.modules import feature


NAT = {
    'state': 'disabled',
    'auto_restart': 'enabled',
    'high_mem_alert': 'disabled',
    'delayed': 'False',
    'has_global_scope': 'true',
    'has_per_asic_scope': 'False',
    'support_syslog_rate_limit': 'true',
}

DATABASE = {
    'state': 'always_enabled',
    'auto_restart': 'always_enabled',
    'high_mem_alert': 'disabled',
    'has_global_scope': 'true',
}

MUX = {
    'state': 'always_disabled',
    'auto_restart': 'enabled',
    'high_mem_alert': 'disabled',
}


def seed(fake_swsscommon):
    fake_swsscommon.seed({'FEATURE': {'nat': NAT, 'database': DATABASE, 'mux': MUX}})


# -- pure logic ------------------------------------------------------------------

def test_build_feature_entry_only_given_fields():
    assert feature.build_feature_entry('nat', NAT, enabled=True) == {'state': 'enabled'}
    assert feature.build_feature_entry('nat', NAT, auto_restart=False, high_mem_alert=True) == {
        'auto_restart': 'disabled', 'high_mem_alert': 'enabled'}


def test_build_feature_entry_unknown_feature():
    with pytest.raises(feature.FeatureError) as excinfo:
        feature.build_feature_entry('bogus', {}, enabled=True)
    assert 'feature "bogus" does not exist' in str(excinfo.value)


@pytest.mark.parametrize('entry,option,field,stored', (
    (DATABASE, 'enabled', 'state', 'always_enabled'),
    (DATABASE, 'auto_restart', 'auto_restart', 'always_enabled'),
    (MUX, 'enabled', 'state', 'always_disabled'),
))
def test_build_feature_entry_locked_field(entry, option, field, stored):
    locked_value = feature.LOCKED_VALUES[stored] == 'enabled'
    # Asking for what the feature already has is not a change.
    assert feature.build_feature_entry('x', entry, **{option: locked_value}) == {}
    with pytest.raises(feature.FeatureError) as excinfo:
        feature.build_feature_entry('x', entry, **{option: not locked_value})
    assert 'feature "x" has %s=%s, which cannot be changed' % (field, stored) in str(excinfo.value)


# -- module runs ------------------------------------------------------------------

@pytest.mark.parametrize('check_mode', (True, False))
def test_enable(fake_swsscommon, run_module, check_mode):
    seed(fake_swsscommon)
    result = run_module(feature, dict(name='nat', enabled=True), check_mode=check_mode)
    after = dict(NAT, state='enabled')
    assert result['changed'] is True
    assert result['name'] == 'nat'
    assert result['state'] == 'enabled'
    assert result['diff'] == {'before': NAT, 'after': after}
    if check_mode:
        assert fake_swsscommon.writes == []
        assert fake_swsscommon.get_entry('FEATURE', 'nat') == NAT
    else:
        # Only the managed field is written; the informational fields are untouched.
        assert fake_swsscommon.writes == [('mod_entry', 'FEATURE', 'nat', {'state': 'enabled'})]
        assert fake_swsscommon.get_entry('FEATURE', 'nat') == after


@pytest.mark.parametrize('check_mode', (True, False))
def test_update_several_fields(fake_swsscommon, run_module, check_mode):
    seed(fake_swsscommon)
    result = run_module(feature, dict(name='nat', auto_restart=False, high_mem_alert=True), check_mode=check_mode)
    after = dict(NAT, auto_restart='disabled', high_mem_alert='enabled')
    assert result['changed'] is True
    assert result['state'] == 'disabled'
    assert result['diff'] == {'before': NAT, 'after': after}
    if check_mode:
        assert fake_swsscommon.writes == []
    else:
        assert fake_swsscommon.writes == [
            ('mod_entry', 'FEATURE', 'nat', {'auto_restart': 'disabled', 'high_mem_alert': 'enabled'})]
        assert fake_swsscommon.get_entry('FEATURE', 'nat') == after


@pytest.mark.parametrize('check_mode', (True, False))
def test_disable_then_idempotent(fake_swsscommon, run_module, check_mode):
    seed(fake_swsscommon)
    fake_swsscommon.seed({'FEATURE': {'nat': dict(NAT, state='enabled')}})
    result = run_module(feature, dict(name='nat', enabled=False))
    assert result['changed'] is True
    assert fake_swsscommon.get_entry('FEATURE', 'nat') == NAT

    result = run_module(feature, dict(name='nat', enabled=False, auto_restart=True), check_mode=check_mode)
    assert result['changed'] is False
    assert result['diff'] == {'before': NAT, 'after': NAT}
    assert fake_swsscommon.writes == [('mod_entry', 'FEATURE', 'nat', {'state': 'disabled'})]


def test_missing_field_is_added(fake_swsscommon, run_module):
    # Older images may lack high_mem_alert; the field is backfilled like `config feature` does.
    fake_swsscommon.seed({'FEATURE': {'snmp': {'state': 'enabled', 'auto_restart': 'enabled'}}})
    result = run_module(feature, dict(name='snmp', high_mem_alert=False))
    assert result['changed'] is True
    assert fake_swsscommon.get_entry('FEATURE', 'snmp') == {
        'state': 'enabled', 'auto_restart': 'enabled', 'high_mem_alert': 'disabled'}


@pytest.mark.parametrize('check_mode', (True, False))
def test_unknown_feature_fails(fake_swsscommon, run_module, check_mode):
    seed(fake_swsscommon)
    result = run_module(feature, dict(name='bogus', enabled=True), check_mode=check_mode, expect_failure=True)
    assert result['msg'] == 'feature "bogus" does not exist on this device; see "show feature status"'
    assert fake_swsscommon.writes == []
    assert not fake_swsscommon.has_entry('FEATURE', 'bogus')


@pytest.mark.parametrize('name,params,msg', (
    ('database', dict(enabled=False), 'feature "database" has state=always_enabled, which cannot be changed to disabled'),
    ('database', dict(auto_restart=False),
     'feature "database" has auto_restart=always_enabled, which cannot be changed to disabled'),
    ('mux', dict(enabled=True), 'feature "mux" has state=always_disabled, which cannot be changed to enabled'),
))
def test_locked_feature_fails(fake_swsscommon, run_module, name, params, msg):
    seed(fake_swsscommon)
    result = run_module(feature, dict(name=name, **params), expect_failure=True)
    assert result['msg'] == msg
    assert fake_swsscommon.writes == []


def test_locked_feature_matching_value_is_not_a_change(fake_swsscommon, run_module):
    seed(fake_swsscommon)
    result = run_module(feature, dict(name='database', enabled=True, auto_restart=True))
    assert result['changed'] is False
    assert result['state'] == 'always_enabled'
    assert fake_swsscommon.writes == []

    # Other fields of a locked feature are still manageable.
    result = run_module(feature, dict(name='mux', enabled=False, auto_restart=False))
    assert result['changed'] is True
    assert fake_swsscommon.writes == [('mod_entry', 'FEATURE', 'mux', {'auto_restart': 'disabled'})]
    assert fake_swsscommon.get_entry('FEATURE', 'mux') == dict(MUX, auto_restart='disabled')


def test_requires_one_option(fake_swsscommon, run_module):
    seed(fake_swsscommon)
    result = run_module(feature, dict(name='nat'), expect_failure=True)
    assert 'one of the following is required' in result['msg']
    assert fake_swsscommon.writes == []
