# -*- coding: utf-8 -*-
#
# GNU General Public License v3.0+ (see https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import (absolute_import, division, print_function)
__metaclass__ = type

import json

import pytest

from ansible_collections.community.sonic.plugins.modules import ntp_key

TABLE = 'NTP_KEY'
SECRET = 'HEX:5c7a3f'
#: base64 of SECRET, which is what SONiC stores and later b64decodes into the key file.
ENCODED = 'SEVYOjVjN2EzZg=='
STORED = {'type': 'sha256', 'value': ENCODED, 'trusted': 'yes'}
MASKED = dict(STORED, value=ntp_key.VALUE_PLACEHOLDER)


def test_encode_value():
    assert ntp_key.encode_value('secret') == 'c2VjcmV0'
    assert ntp_key.encode_value(SECRET) == ENCODED


def test_build_key_entry():
    assert ntp_key.build_key_entry() == {}
    assert ntp_key.build_key_entry(key_type='md5', value='secret', trusted=False) == {
        'type': 'md5', 'value': 'c2VjcmV0', 'trusted': 'no'}
    assert ntp_key.build_key_entry(trusted=True) == {'trusted': 'yes'}


def test_mask_value():
    assert ntp_key.mask_value({}) == {}
    assert ntp_key.mask_value({'type': 'md5'}) == {'type': 'md5'}
    assert ntp_key.mask_value(STORED) == MASKED


@pytest.mark.parametrize('check_mode', (True, False))
def test_create(fake_swsscommon, run_module, check_mode):
    result = run_module(ntp_key, dict(id=42, type='sha256', value=SECRET, trusted=True), check_mode=check_mode)
    assert result['changed'] is True
    assert result['id'] == 42
    assert result['diff'] == {'before': {}, 'after': MASKED}
    assert SECRET not in json.dumps(result)
    assert ENCODED not in json.dumps(result)
    if check_mode:
        assert fake_swsscommon.writes == []
        assert not fake_swsscommon.has_entry(TABLE, '42')
    else:
        assert fake_swsscommon.writes == [('mod_entry', TABLE, '42', STORED)]
        assert fake_swsscommon.get_entry(TABLE, '42') == STORED


def test_create_with_value_only(fake_swsscommon, run_module):
    result = run_module(ntp_key, dict(id=1, value='secret'))
    assert result['changed'] is True
    assert fake_swsscommon.get_entry(TABLE, '1') == {'value': 'c2VjcmV0'}


@pytest.mark.parametrize('check_mode', (True, False))
def test_idempotent(fake_swsscommon, run_module, check_mode):
    fake_swsscommon.seed({TABLE: {'42': STORED}})
    result = run_module(ntp_key, dict(id=42, type='sha256', value=SECRET, trusted=True), check_mode=check_mode)
    assert result['changed'] is False
    assert result['diff'] == {'before': MASKED, 'after': MASKED}
    assert fake_swsscommon.writes == []


@pytest.mark.parametrize('check_mode', (True, False))
def test_update_without_value(fake_swsscommon, run_module, check_mode):
    fake_swsscommon.seed({TABLE: {'42': STORED}})
    result = run_module(ntp_key, dict(id=42, trusted=False), check_mode=check_mode)
    assert result['changed'] is True
    assert result['diff'] == {'before': MASKED, 'after': dict(MASKED, trusted='no')}
    if check_mode:
        assert fake_swsscommon.writes == []
        assert fake_swsscommon.get_entry(TABLE, '42') == STORED
    else:
        assert fake_swsscommon.writes == [('mod_entry', TABLE, '42', {'trusted': 'no'})]
        assert fake_swsscommon.get_entry(TABLE, '42') == dict(STORED, trusted='no')


def test_change_value(fake_swsscommon, run_module):
    fake_swsscommon.seed({TABLE: {'42': STORED}})
    result = run_module(ntp_key, dict(id=42, value='other'))
    assert result['changed'] is True
    assert result['diff'] == {'before': MASKED, 'after': MASKED}
    assert fake_swsscommon.get_entry(TABLE, '42') == dict(STORED, value='b3RoZXI=')


@pytest.mark.parametrize('check_mode', (True, False))
def test_remove(fake_swsscommon, run_module, check_mode):
    fake_swsscommon.seed({TABLE: {'42': STORED, '7': {'type': 'md5', 'value': 'c2VjcmV0'}}})
    result = run_module(ntp_key, dict(id=42, state='absent'), check_mode=check_mode)
    assert result['changed'] is True
    assert result['diff'] == {'before': MASKED, 'after': {}}
    assert ENCODED not in json.dumps(result)
    if check_mode:
        assert fake_swsscommon.writes == []
        assert fake_swsscommon.has_entry(TABLE, '42')
    else:
        assert fake_swsscommon.writes == [('set_entry', TABLE, '42', None)]
        assert not fake_swsscommon.has_entry(TABLE, '42')
        assert fake_swsscommon.has_entry(TABLE, '7')


def test_remove_absent_key_is_noop(fake_swsscommon, run_module):
    result = run_module(ntp_key, dict(id=42, state='absent'))
    assert result['changed'] is False
    assert result['diff'] == {'before': {}, 'after': {}}
    assert fake_swsscommon.writes == []


def test_create_without_value_fails(fake_swsscommon, run_module):
    result = run_module(ntp_key, dict(id=42, trusted=True), expect_failure=True)
    assert 'NTP key 42 does not exist yet, so value is required' in result['msg']
    assert fake_swsscommon.writes == []


def test_empty_value_fails(fake_swsscommon, run_module):
    result = run_module(ntp_key, dict(id=42, value=''), expect_failure=True)
    assert 'value must not be empty' in result['msg']
    assert fake_swsscommon.writes == []


@pytest.mark.parametrize('key_id', (0, 65536))
def test_invalid_id_fails(fake_swsscommon, run_module, key_id):
    result = run_module(ntp_key, dict(id=key_id, value='secret'), expect_failure=True)
    assert 'id must be between 1 and 65535' in result['msg']
    assert fake_swsscommon.writes == []


def test_invalid_type_fails(fake_swsscommon, run_module):
    result = run_module(ntp_key, dict(id=42, type='crc32', value='secret'), expect_failure=True)
    assert 'type' in result['msg']
    assert fake_swsscommon.writes == []
