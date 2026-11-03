# -*- coding: utf-8 -*-
#
# GNU General Public License v3.0+ (see https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import (absolute_import, division, print_function)
__metaclass__ = type

import pytest

from ansible_collections.community.sonic.plugins.modules import gnmi_client_cert


TABLE = 'GNMI_CLIENT_CERT'
CN = 'collector.example.net'


# -- pure logic ------------------------------------------------------------------

def test_build_client_cert_entry():
    assert gnmi_client_cert.build_client_cert_entry('present', ['gnmi_readonly']) == {'role': ['gnmi_readonly']}
    assert gnmi_client_cert.build_client_cert_entry('present', ['gnmi_readwrite', 'gnmi_readonly', 'gnmi_readonly']) == {
        'role': ['gnmi_readwrite', 'gnmi_readonly']}
    assert gnmi_client_cert.build_client_cert_entry('absent') is None
    with pytest.raises(ValueError, match='at least one role'):
        gnmi_client_cert.build_client_cert_entry('present', ['', '  '])


# -- module runs ------------------------------------------------------------------

@pytest.mark.parametrize('check_mode', (True, False))
def test_create(fake_swsscommon, run_module, check_mode):
    result = run_module(gnmi_client_cert, dict(common_name=CN, role='gnmi_readonly'), check_mode=check_mode)
    assert result['changed'] is True
    assert result['common_name'] == CN
    assert result['role'] == ['gnmi_readonly']
    assert result['diff'] == {'before': {}, 'after': {'role': ['gnmi_readonly']}}
    if check_mode:
        assert fake_swsscommon.writes == []
        assert not fake_swsscommon.has_entry(TABLE, CN)
    else:
        assert fake_swsscommon.writes == [('set_entry', TABLE, CN, {'role': ['gnmi_readonly']})]
        # Stored as a comma separated role@ list, as the gNMI daemon expects.
        assert fake_swsscommon.store[TABLE][CN] == {'role@': 'gnmi_readonly'}
        assert fake_swsscommon.get_entry(TABLE, CN) == {'role': ['gnmi_readonly']}


@pytest.mark.parametrize('check_mode', (True, False))
def test_idempotent(fake_swsscommon, run_module, check_mode):
    fake_swsscommon.seed({TABLE: {CN: {'role': ['gnmi_readonly', 'gnmi_readwrite']}}})
    result = run_module(gnmi_client_cert, dict(cn=CN, roles=['gnmi_readonly', 'gnmi_readwrite']), check_mode=check_mode)
    assert result['changed'] is False
    assert result['role'] == ['gnmi_readonly', 'gnmi_readwrite']
    assert result['diff']['before'] == result['diff']['after'] == {'role': ['gnmi_readonly', 'gnmi_readwrite']}
    assert fake_swsscommon.writes == []


@pytest.mark.parametrize('check_mode', (True, False))
def test_update_replaces_roles(fake_swsscommon, run_module, check_mode):
    fake_swsscommon.seed({TABLE: {CN: {'role': ['gnmi_readonly']}}})
    result = run_module(gnmi_client_cert, dict(common_name=CN, role=['gnmi_readwrite']), check_mode=check_mode)
    assert result['changed'] is True
    assert result['role'] == ['gnmi_readwrite']
    assert result['diff'] == {'before': {'role': ['gnmi_readonly']}, 'after': {'role': ['gnmi_readwrite']}}
    if check_mode:
        assert fake_swsscommon.writes == []
        assert fake_swsscommon.get_entry(TABLE, CN) == {'role': ['gnmi_readonly']}
    else:
        assert fake_swsscommon.writes == [('set_entry', TABLE, CN, {'role': ['gnmi_readwrite']})]
        assert fake_swsscommon.store[TABLE][CN] == {'role@': 'gnmi_readwrite'}


@pytest.mark.parametrize('check_mode', (True, False))
def test_absent(fake_swsscommon, run_module, check_mode):
    fake_swsscommon.seed({TABLE: {CN: {'role': ['gnmi_readonly']}, 'other.example.net': {'role': ['gnmi_readwrite']}}})
    result = run_module(gnmi_client_cert, dict(common_name=CN, state='absent'), check_mode=check_mode)
    assert result['changed'] is True
    assert result['role'] == []
    assert result['diff'] == {'before': {'role': ['gnmi_readonly']}, 'after': {}}
    if check_mode:
        assert fake_swsscommon.writes == []
        assert fake_swsscommon.has_entry(TABLE, CN)
    else:
        assert fake_swsscommon.writes == [('set_entry', TABLE, CN, None)]
        assert not fake_swsscommon.has_entry(TABLE, CN)
    assert fake_swsscommon.get_entry(TABLE, 'other.example.net') == {'role': ['gnmi_readwrite']}


def test_absent_when_missing_is_not_a_change(fake_swsscommon, run_module):
    result = run_module(gnmi_client_cert, dict(common_name=CN, state='absent'))
    assert result['changed'] is False
    assert result['diff'] == {'before': {}, 'after': {}}
    assert fake_swsscommon.writes == []


def test_present_requires_role(fake_swsscommon, run_module):
    result = run_module(gnmi_client_cert, dict(common_name=CN), expect_failure=True)
    assert 'state is present but all of the following are missing: role' in result['msg']
    assert fake_swsscommon.writes == []


@pytest.mark.parametrize('params,msg', (
    (dict(common_name='  ', role='gnmi_readonly'), 'common_name must not be empty'),
    (dict(common_name=CN, role=['']), 'at least one role is required'),
))
def test_invalid_values_fail(fake_swsscommon, run_module, params, msg):
    result = run_module(gnmi_client_cert, params, expect_failure=True)
    assert result['msg'] == msg
    assert fake_swsscommon.writes == []
