# -*- coding: utf-8 -*-
#
# GNU General Public License v3.0+ (see https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import (absolute_import, division, print_function)
__metaclass__ = type

import pytest

from ansible_collections.community.sonic.plugins.modules import gnmi_server


GNMI_FEATURE = {'FEATURE': {'gnmi': {'state': 'enabled'}, 'lldp': {'state': 'enabled'}}}
TELEMETRY_FEATURE = {'FEATURE': {'telemetry': {'state': 'enabled'}, 'lldp': {'state': 'enabled'}}}

SERVER = {'client_auth': 'true', 'log_level': '2', 'port': '50052', 'user_auth': 'cert'}
CERTS = {
    'ca_crt': '/etc/sonic/telemetry/dsmsroot.cer',
    'server_crt': '/etc/sonic/telemetry/streamingtelemetryserver.cer',
    'server_key': '/etc/sonic/telemetry/streamingtelemetryserver.key',
}


def diff(before_server, before_certs, after_server, after_certs):
    return {'before': {'gnmi': before_server, 'certs': before_certs},
            'after': {'gnmi': after_server, 'certs': after_certs}}


# -- pure logic ------------------------------------------------------------------

def test_detect_table():
    assert gnmi_server.detect_table(['gnmi', 'lldp']) == 'GNMI'
    assert gnmi_server.detect_table(['telemetry', 'lldp']) == 'TELEMETRY'
    assert gnmi_server.detect_table(['gnmi', 'telemetry']) == 'GNMI'
    assert gnmi_server.detect_table([]) == 'TELEMETRY'


def test_join_user_auth():
    assert gnmi_server.join_user_auth(['cert']) == 'cert'
    assert gnmi_server.join_user_auth(['password', 'jwt', 'cert', 'jwt']) == 'password,jwt,cert'
    assert gnmi_server.join_user_auth(['none']) == 'none'
    with pytest.raises(ValueError, match='"none" cannot be combined'):
        gnmi_server.join_user_auth(['none', 'cert'])
    with pytest.raises(ValueError, match='at least one method'):
        gnmi_server.join_user_auth([])


def test_build_entries_only_given_fields():
    assert gnmi_server.build_server_entry() == {}
    assert gnmi_server.build_server_entry(port=50052, client_auth=False, user_auth='password,jwt') == {
        'port': 50052, 'client_auth': False, 'user_auth': 'password,jwt'}
    assert gnmi_server.build_server_entry(log_level=0, save_on_set=True, enable_crl=True, crl_expire_duration=3600) == {
        'log_level': 0, 'save_on_set': True, 'enable_crl': True, 'crl_expire_duration': 3600}
    assert gnmi_server.build_certs_entry() == {}
    assert gnmi_server.build_certs_entry(ca_cert='/a.cer', server_cert='', server_key='/k.key') == {
        'ca_crt': '/a.cer', 'server_crt': None, 'server_key': '/k.key'}


# -- module runs ------------------------------------------------------------------

@pytest.mark.parametrize('check_mode', (True, False))
def test_create_server_and_certs(fake_swsscommon, run_module, check_mode):
    fake_swsscommon.seed(GNMI_FEATURE)
    params = dict(port=50052, client_auth=True, user_auth=['cert'], log_level=2,
                  ca_cert=CERTS['ca_crt'], server_cert=CERTS['server_crt'], server_key=CERTS['server_key'])
    result = run_module(gnmi_server, params, check_mode=check_mode)
    assert result['changed'] is True
    assert result['table'] == 'GNMI'
    assert result['diff'] == diff({}, {}, SERVER, CERTS)
    if check_mode:
        assert fake_swsscommon.writes == []
        assert not fake_swsscommon.has_entry('GNMI', 'gnmi')
    else:
        assert fake_swsscommon.writes == [
            ('mod_entry', 'GNMI', 'gnmi', SERVER),
            ('mod_entry', 'GNMI', 'certs', CERTS),
        ]
        assert fake_swsscommon.get_entry('GNMI', 'gnmi') == SERVER
        assert fake_swsscommon.get_entry('GNMI', 'certs') == CERTS


@pytest.mark.parametrize('check_mode', (True, False))
def test_idempotent(fake_swsscommon, run_module, check_mode):
    fake_swsscommon.seed(GNMI_FEATURE)
    fake_swsscommon.seed({'GNMI': {'gnmi': SERVER, 'certs': CERTS}})
    params = dict(port=50052, client_auth=True, user_auth=['cert'], log_level=2,
                  ca_cert=CERTS['ca_crt'], server_cert=CERTS['server_crt'], server_key=CERTS['server_key'])
    result = run_module(gnmi_server, params, check_mode=check_mode)
    assert result['changed'] is False
    assert result['diff'] == diff(SERVER, CERTS, SERVER, CERTS)
    assert fake_swsscommon.writes == []


@pytest.mark.parametrize('check_mode', (True, False))
def test_update_only_given_fields(fake_swsscommon, run_module, check_mode):
    fake_swsscommon.seed(GNMI_FEATURE)
    fake_swsscommon.seed({'GNMI': {'gnmi': dict(SERVER, threshold='100'), 'certs': CERTS}})
    result = run_module(gnmi_server, dict(port=8080, user_auth=['password', 'jwt', 'cert'], save_on_set=False),
                        check_mode=check_mode)
    after = dict(SERVER, threshold='100', port='8080', user_auth='password,jwt,cert', save_on_set='false')
    assert result['changed'] is True
    assert result['diff'] == diff(dict(SERVER, threshold='100'), CERTS, after, CERTS)
    if check_mode:
        assert fake_swsscommon.writes == []
    else:
        # Only the given fields are written; certs is not touched at all.
        assert fake_swsscommon.writes == [
            ('mod_entry', 'GNMI', 'gnmi', {'port': '8080', 'user_auth': 'password,jwt,cert', 'save_on_set': 'false'})]
        assert fake_swsscommon.get_entry('GNMI', 'gnmi') == after
        assert fake_swsscommon.get_entry('GNMI', 'certs') == CERTS


@pytest.mark.parametrize('check_mode', (True, False))
def test_clear_cert_paths(fake_swsscommon, run_module, check_mode):
    fake_swsscommon.seed(GNMI_FEATURE)
    fake_swsscommon.seed({'GNMI': {'gnmi': SERVER, 'certs': CERTS}})
    result = run_module(gnmi_server, dict(ca_cert='', server_cert=''), check_mode=check_mode)
    after_certs = {'server_key': CERTS['server_key']}
    assert result['changed'] is True
    assert result['diff'] == diff(SERVER, CERTS, SERVER, after_certs)
    if check_mode:
        assert fake_swsscommon.writes == []
    else:
        assert fake_swsscommon.writes == [('set_entry', 'GNMI', 'certs', after_certs)]
        assert fake_swsscommon.get_entry('GNMI', 'certs') == after_certs


def test_clearing_absent_certs_is_not_a_change(fake_swsscommon, run_module):
    fake_swsscommon.seed(GNMI_FEATURE)
    fake_swsscommon.seed({'GNMI': {'gnmi': SERVER}})
    result = run_module(gnmi_server, dict(ca_cert='', server_cert='', server_key=''))
    assert result['changed'] is False
    assert result['diff'] == diff(SERVER, {}, SERVER, {})
    assert fake_swsscommon.writes == []
    assert not fake_swsscommon.has_entry('GNMI', 'certs')


@pytest.mark.parametrize('check_mode', (True, False))
def test_absent(fake_swsscommon, run_module, check_mode):
    fake_swsscommon.seed(GNMI_FEATURE)
    fake_swsscommon.seed({'GNMI': {'gnmi': SERVER, 'certs': CERTS}})
    result = run_module(gnmi_server, dict(state='absent'), check_mode=check_mode)
    assert result['changed'] is True
    assert result['diff'] == diff(SERVER, CERTS, {}, {})
    if check_mode:
        assert fake_swsscommon.writes == []
        assert fake_swsscommon.get_entry('GNMI', 'gnmi') == SERVER
    else:
        assert fake_swsscommon.writes == [
            ('set_entry', 'GNMI', 'gnmi', None),
            ('set_entry', 'GNMI', 'certs', None),
        ]
        assert fake_swsscommon.get_table('GNMI') == {}

    result = run_module(gnmi_server, dict(state='absent'), check_mode=check_mode)
    assert result['changed'] is check_mode


def test_absent_when_missing_is_not_a_change(fake_swsscommon, run_module):
    fake_swsscommon.seed(GNMI_FEATURE)
    result = run_module(gnmi_server, dict(state='absent'))
    assert result['changed'] is False
    assert result['diff'] == diff({}, {}, {}, {})
    assert fake_swsscommon.writes == []


def test_legacy_telemetry_table_is_detected(fake_swsscommon, run_module):
    fake_swsscommon.seed(TELEMETRY_FEATURE)
    fake_swsscommon.seed({'TELEMETRY': {'gnmi': {'port': '8080'}}})
    result = run_module(gnmi_server, dict(port=8080, client_auth=False))
    assert result['changed'] is True
    assert result['table'] == 'TELEMETRY'
    assert fake_swsscommon.writes == [('mod_entry', 'TELEMETRY', 'gnmi', {'port': '8080', 'client_auth': 'false'})]
    assert fake_swsscommon.get_entry('TELEMETRY', 'gnmi') == {'port': '8080', 'client_auth': 'false'}
    assert not fake_swsscommon.has_entry('GNMI', 'gnmi')


def test_table_override(fake_swsscommon, run_module):
    fake_swsscommon.seed(GNMI_FEATURE)
    result = run_module(gnmi_server, dict(table='TELEMETRY', port=8080))
    assert result['table'] == 'TELEMETRY'
    assert fake_swsscommon.writes == [('mod_entry', 'TELEMETRY', 'gnmi', {'port': '8080'})]
    assert not fake_swsscommon.has_entry('GNMI', 'gnmi')


@pytest.mark.parametrize('params,msg', (
    (dict(port=0), 'port must be between 1 and 65535, got 0'),
    (dict(port=70000), 'port must be between 1 and 65535, got 70000'),
    (dict(log_level=101), 'log_level must be between 0 and 100, got 101'),
    (dict(crl_expire_duration=-1), 'crl_expire_duration must not be negative, got -1'),
    (dict(user_auth=['none', 'cert']), 'user_auth "none" cannot be combined with other methods'),
    (dict(user_auth=[]), 'user_auth must list at least one method'),
))
def test_invalid_values_fail(fake_swsscommon, run_module, params, msg):
    fake_swsscommon.seed(GNMI_FEATURE)
    result = run_module(gnmi_server, params, expect_failure=True)
    assert result['msg'] == msg
    assert fake_swsscommon.writes == []


def test_unknown_user_auth_fails(fake_swsscommon, run_module):
    fake_swsscommon.seed(GNMI_FEATURE)
    result = run_module(gnmi_server, dict(user_auth=['kerberos']), expect_failure=True)
    assert 'user_auth' in result['msg']
    assert fake_swsscommon.writes == []


def test_requires_an_option(fake_swsscommon, run_module):
    fake_swsscommon.seed(GNMI_FEATURE)
    result = run_module(gnmi_server, dict(table='GNMI'), expect_failure=True)
    assert 'state is present but any of the following are missing' in result['msg']
    assert fake_swsscommon.writes == []
