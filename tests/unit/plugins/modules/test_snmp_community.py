# -*- coding: utf-8 -*-
#
# GNU General Public License v3.0+ (see https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import (absolute_import, division, print_function)
__metaclass__ = type

import json

import pytest

from ansible_collections.community.sonic.plugins.modules import snmp_community


SECRET = 'v3ry-s3cret-c0mmun1ty'


def assert_secret_not_in(result):
    """The community string must never appear anywhere in a module result or failure."""
    assert SECRET not in json.dumps(result)


# -- pure logic ------------------------------------------------------------------

def test_validate_community_accepts_cli_valid_strings():
    snmp_community.validate_community('public')
    snmp_community.validate_community('a')
    snmp_community.validate_community('x' * 32)
    snmp_community.validate_community('with spaces and $ymbols!')


@pytest.mark.parametrize('name,message', (
    ('', 'the community string must be 1 to 32 characters long'),
    ('x' * 33, 'the community string must be 1 to 32 characters long'),
    ('user@host', 'the community string must not contain "@" or ":"'),
    ('a:b', 'the community string must not contain "@" or ":"'),
))
def test_validate_community_rejects(name, message):
    with pytest.raises(ValueError) as excinfo:
        snmp_community.validate_community(name)
    assert str(excinfo.value) == message
    assert name not in str(excinfo.value) or name == ''


def test_build_community_entry():
    assert snmp_community.build_community_entry('RO', 'present') == {'TYPE': 'RO'}
    assert snmp_community.build_community_entry('RW', 'present') == {'TYPE': 'RW'}
    assert snmp_community.build_community_entry('RW', 'absent') is None


# -- module runs ------------------------------------------------------------------

@pytest.mark.parametrize('check_mode', (True, False))
def test_create_read_only_by_default(fake_swsscommon, run_module, check_mode):
    result = run_module(snmp_community, dict(name=SECRET), check_mode=check_mode)
    assert result['changed'] is True
    assert result['type'] == 'RO'
    assert result['diff'] == {'before': {}, 'after': {'TYPE': 'RO'}}
    assert_secret_not_in(result)
    if check_mode:
        assert fake_swsscommon.writes == []
        assert not fake_swsscommon.has_entry('SNMP_COMMUNITY', SECRET)
    else:
        assert fake_swsscommon.writes == [('set_entry', 'SNMP_COMMUNITY', SECRET, {'TYPE': 'RO'})]
        assert fake_swsscommon.get_entry('SNMP_COMMUNITY', SECRET) == {'TYPE': 'RO'}


@pytest.mark.parametrize('check_mode', (True, False))
def test_idempotent(fake_swsscommon, run_module, check_mode):
    fake_swsscommon.seed({'SNMP_COMMUNITY': {SECRET: {'TYPE': 'RW'}, 'public': {'TYPE': 'RO'}}})
    result = run_module(snmp_community, dict(name=SECRET, type='RW'), check_mode=check_mode)
    assert result['changed'] is False
    assert result['type'] == 'RW'
    assert result['diff'] == {'before': {'TYPE': 'RW'}, 'after': {'TYPE': 'RW'}}
    assert_secret_not_in(result)
    assert fake_swsscommon.writes == []


@pytest.mark.parametrize('check_mode', (True, False))
def test_change_type(fake_swsscommon, run_module, check_mode):
    fake_swsscommon.seed({'SNMP_COMMUNITY': {SECRET: {'TYPE': 'RO'}, 'public': {'TYPE': 'RO'}}})
    result = run_module(snmp_community, dict(name=SECRET, type='RW'), check_mode=check_mode)
    assert result['changed'] is True
    assert result['type'] == 'RW'
    assert result['diff'] == {'before': {'TYPE': 'RO'}, 'after': {'TYPE': 'RW'}}
    assert_secret_not_in(result)
    if check_mode:
        assert fake_swsscommon.writes == []
        assert fake_swsscommon.get_entry('SNMP_COMMUNITY', SECRET) == {'TYPE': 'RO'}
    else:
        assert fake_swsscommon.writes == [('set_entry', 'SNMP_COMMUNITY', SECRET, {'TYPE': 'RW'})]
        assert fake_swsscommon.get_entry('SNMP_COMMUNITY', SECRET) == {'TYPE': 'RW'}
    # Other communities are untouched.
    assert fake_swsscommon.get_entry('SNMP_COMMUNITY', 'public') == {'TYPE': 'RO'}


@pytest.mark.parametrize('check_mode', (True, False))
def test_remove(fake_swsscommon, run_module, check_mode):
    fake_swsscommon.seed({'SNMP_COMMUNITY': {SECRET: {'TYPE': 'RO'}, 'public': {'TYPE': 'RO'}}})
    result = run_module(snmp_community, dict(name=SECRET, state='absent'), check_mode=check_mode)
    assert result['changed'] is True
    assert 'type' not in result
    assert result['diff'] == {'before': {'TYPE': 'RO'}, 'after': {}}
    assert_secret_not_in(result)
    if check_mode:
        assert fake_swsscommon.writes == []
        assert fake_swsscommon.has_entry('SNMP_COMMUNITY', SECRET)
    else:
        assert fake_swsscommon.writes == [('set_entry', 'SNMP_COMMUNITY', SECRET, None)]
        assert not fake_swsscommon.has_entry('SNMP_COMMUNITY', SECRET)
    assert fake_swsscommon.get_entry('SNMP_COMMUNITY', 'public') == {'TYPE': 'RO'}


@pytest.mark.parametrize('check_mode', (True, False))
def test_remove_when_absent_is_not_a_change(fake_swsscommon, run_module, check_mode):
    result = run_module(snmp_community, dict(name=SECRET, state='absent', type='RW'), check_mode=check_mode)
    assert result['changed'] is False
    assert result['diff'] == {'before': {}, 'after': {}}
    assert_secret_not_in(result)
    assert fake_swsscommon.writes == []


@pytest.mark.parametrize('name,message', (
    ('x' * 33, 'the community string must be 1 to 32 characters long'),
    (SECRET + '@host', 'the community string must not contain "@" or ":"'),
))
def test_invalid_community_fails_without_echoing_it(fake_swsscommon, run_module, name, message):
    result = run_module(snmp_community, dict(name=name), expect_failure=True)
    assert result['msg'] == message
    assert_secret_not_in(result)
    assert fake_swsscommon.writes == []


def test_invalid_type_is_rejected(fake_swsscommon, run_module):
    result = run_module(snmp_community, dict(name=SECRET, type='ro'), expect_failure=True)
    assert 'value of type must be one of: RO, RW' in result['msg']
    assert fake_swsscommon.writes == []


def test_name_option_is_no_log(fake_swsscommon, run_module, monkeypatch):
    created = []
    real_ansible_module = snmp_community.AnsibleModule

    class RecordingAnsibleModule(real_ansible_module):
        def __init__(self, *args, **kwargs):
            super(RecordingAnsibleModule, self).__init__(*args, **kwargs)
            created.append(self)

    monkeypatch.setattr(snmp_community, 'AnsibleModule', RecordingAnsibleModule)
    run_module(snmp_community, dict(name=SECRET))
    assert created[0].argument_spec['name']['no_log'] is True
    assert SECRET in created[0].no_log_values
