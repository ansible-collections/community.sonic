# -*- coding: utf-8 -*-
#
# GNU General Public License v3.0+ (see https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import (absolute_import, division, print_function)
__metaclass__ = type

import pytest

from ansible_collections.community.sonic.plugins.modules import device_metadata


LOCALHOST = {
    'hostname': 'sonic',
    'hwsku': 'Force10-S6000',
    'platform': 'x86_64-kvm_x86_64-r0',
    'mac': '52:54:00:12:34:56',
    'type': 'LeafRouter',
    'bgp_asn': '65100',
    'default_bgp_status': 'up',
    'default_pfcwd_status': 'disable',
    'buffer_model': 'traditional',
}


def seed(fake_swsscommon, entry=None):
    fake_swsscommon.seed({'DEVICE_METADATA': {'localhost': dict(entry if entry is not None else LOCALHOST)}})


# -- pure helpers -------------------------------------------------------------

@pytest.mark.parametrize('hostname', ('sonic', 'leaf-1', 'leaf1.example.com', 'a', '1a', 'A' * 63))
def test_validate_hostname_accepts(hostname):
    assert device_metadata.validate_hostname(hostname) == hostname


@pytest.mark.parametrize('hostname', ('', '-leaf', 'leaf-', 'leaf_1', 'leaf 1', 'leaf..1', 'A' * 64, 'a.' * 127 + 'a'))
def test_validate_hostname_rejects(hostname):
    with pytest.raises(device_metadata.ValidationError):
        device_metadata.validate_hostname(hostname)


def test_validate_mac_normalises_case():
    assert device_metadata.validate_mac('02:AB:cd:00:00:01') == '02:ab:cd:00:00:01'


@pytest.mark.parametrize('mac', ('', '02-00-00-00-00-01', '0200.0000.0001', '02:00:00:00:00', '02:00:00:00:00:0g'))
def test_validate_mac_rejects(mac):
    with pytest.raises(device_metadata.ValidationError):
        device_metadata.validate_mac(mac)


@pytest.mark.parametrize('asn', (0, -1, 4294967296))
def test_validate_bgp_asn_rejects(asn):
    with pytest.raises(device_metadata.ValidationError):
        device_metadata.validate_bgp_asn(asn)


def test_validate_timezone_known():
    assert device_metadata.validate_timezone('UTC', available={'UTC', 'Europe/Stockholm'}) == 'UTC'
    assert device_metadata.validate_timezone('Europe/Stockholm') == 'Europe/Stockholm'


def test_validate_timezone_unknown():
    with pytest.raises(device_metadata.ValidationError, match='not a known zoneinfo name'):
        device_metadata.validate_timezone('Mars/Olympus', available={'UTC'})


def test_validate_timezone_without_zone_database_checks_shape_only():
    assert device_metadata.validate_timezone('Mars/Olympus', available=set()) == 'Mars/Olympus'
    with pytest.raises(device_metadata.ValidationError, match='not a valid zoneinfo name'):
        device_metadata.validate_timezone('../etc/passwd', available=set())


def test_build_entry_only_includes_given_fields():
    desired = device_metadata.build_device_metadata_entry(dict(hostname='leaf1', bgp_asn=65000, mac='02:00:00:00:00:AA',
                                                               timezone=None, hwsku='Foo'))
    assert desired == {'hostname': 'leaf1', 'bgp_asn': 65000, 'mac': '02:00:00:00:00:aa'}


# -- module runs ----------------------------------------------------------------

@pytest.mark.parametrize('check_mode', (True, False))
def test_set_hostname_merges_into_entry(fake_swsscommon, run_module, check_mode):
    seed(fake_swsscommon)
    result = run_module(device_metadata, dict(hostname='leaf1'), check_mode=check_mode)
    expected = dict(LOCALHOST, hostname='leaf1')
    assert result['changed'] is True
    assert result['diff'] == {'before': LOCALHOST, 'after': expected}
    assert result['entry'] == expected
    if check_mode:
        assert fake_swsscommon.writes == []
        assert fake_swsscommon.get_entry('DEVICE_METADATA', 'localhost') == LOCALHOST
    else:
        assert fake_swsscommon.writes == [('mod_entry', 'DEVICE_METADATA', 'localhost', {'hostname': 'leaf1'})]
        assert fake_swsscommon.get_entry('DEVICE_METADATA', 'localhost') == expected


@pytest.mark.parametrize('check_mode', (True, False))
def test_idempotent(fake_swsscommon, run_module, check_mode):
    seed(fake_swsscommon)
    result = run_module(device_metadata, dict(hostname='sonic', bgp_asn=65100, mac='52:54:00:12:34:56',
                                              default_bgp_status='up', buffer_model='traditional'),
                        check_mode=check_mode)
    assert result['changed'] is False
    assert result['diff'] == {'before': LOCALHOST, 'after': LOCALHOST}
    assert fake_swsscommon.writes == []


def test_second_run_is_unchanged(fake_swsscommon, run_module):
    seed(fake_swsscommon)
    params = dict(hostname='leaf1', timezone='Europe/Stockholm', type='ToRRouter', synchronous_mode='enable',
                  default_pfcwd_status='enable', bgp_asn=4200000000)
    first = run_module(device_metadata, params)
    second = run_module(device_metadata, params)
    assert first['changed'] is True
    assert second['changed'] is False
    assert second['diff']['before'] == first['diff']['after']
    entry = fake_swsscommon.get_entry('DEVICE_METADATA', 'localhost')
    assert entry['timezone'] == 'Europe/Stockholm'
    assert entry['type'] == 'ToRRouter'
    assert entry['synchronous_mode'] == 'enable'
    assert entry['default_pfcwd_status'] == 'enable'
    assert entry['bgp_asn'] == '4200000000'
    # Fields the module does not manage are untouched.
    assert entry['hwsku'] == LOCALHOST['hwsku']
    assert entry['platform'] == LOCALHOST['platform']
    assert len(fake_swsscommon.writes) == 1


def test_creates_entry_when_missing(fake_swsscommon, run_module):
    result = run_module(device_metadata, dict(hostname='leaf1', timezone='UTC'))
    assert result['changed'] is True
    assert result['diff'] == {'before': {}, 'after': {'hostname': 'leaf1', 'timezone': 'UTC'}}
    assert fake_swsscommon.get_entry('DEVICE_METADATA', 'localhost') == {'hostname': 'leaf1', 'timezone': 'UTC'}


def test_mac_is_compared_case_insensitively(fake_swsscommon, run_module):
    seed(fake_swsscommon)
    result = run_module(device_metadata, dict(mac='52:54:00:12:34:56'.upper()))
    assert result['changed'] is False
    assert fake_swsscommon.writes == []


@pytest.mark.parametrize('field', ('hwsku', 'platform'))
def test_refuses_to_change_protected_fields(fake_swsscommon, run_module, field):
    seed(fake_swsscommon)
    result = run_module(device_metadata, {field: 'Something-Else', 'hostname': 'leaf1'}, expect_failure=True)
    assert result['failed'] is True
    assert 'refusing to change %s' % field in result['msg']
    assert device_metadata.HWSKU_ISSUE_URL in result['msg']
    assert fake_swsscommon.writes == []


@pytest.mark.parametrize('check_mode', (True, False))
def test_matching_protected_fields_are_accepted(fake_swsscommon, run_module, check_mode):
    seed(fake_swsscommon)
    result = run_module(device_metadata, dict(hwsku=LOCALHOST['hwsku'], platform=LOCALHOST['platform']),
                        check_mode=check_mode)
    assert result['changed'] is False
    assert result['diff'] == {'before': LOCALHOST, 'after': LOCALHOST}
    assert fake_swsscommon.writes == []


@pytest.mark.parametrize('params,match', (
    (dict(hostname='-bad'), 'hostname "-bad" is not valid'),
    (dict(mac='not-a-mac'), 'mac "not-a-mac" is not a valid MAC address'),
    (dict(bgp_asn=0), 'bgp_asn 0 is out of range'),
    (dict(timezone='Mars/Olympus'), 'timezone "Mars/Olympus" is not'),
))
def test_invalid_values_fail_before_writing(fake_swsscommon, run_module, params, match):
    seed(fake_swsscommon)
    result = run_module(device_metadata, params, expect_failure=True)
    assert result['failed'] is True
    assert match in result['msg']
    assert fake_swsscommon.writes == []


def test_requires_at_least_one_option(fake_swsscommon, run_module):
    seed(fake_swsscommon)
    result = run_module(device_metadata, dict(), expect_failure=True)
    assert result['failed'] is True
    assert 'one of the following is required' in result['msg']
    assert fake_swsscommon.writes == []
