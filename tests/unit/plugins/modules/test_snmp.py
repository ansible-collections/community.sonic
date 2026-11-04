# -*- coding: utf-8 -*-
#
# GNU General Public License v3.0+ (see https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import (absolute_import, division, print_function)
__metaclass__ = type

import pytest

from ansible_collections.community.sonic.plugins.modules import snmp


LOCATION = {'Location': 'Rack 12, Example DC'}
CONTACT = {'noc': 'noc@example.net'}
NOC = {'name': 'noc', 'email': 'noc@example.net'}


def seed(fake_swsscommon, location=True, contact=True):
    entries = {}
    if location:
        entries['LOCATION'] = dict(LOCATION)
    if contact:
        entries['CONTACT'] = dict(CONTACT)
    fake_swsscommon.seed({'SNMP': entries})
    return entries


# -- pure logic ------------------------------------------------------------------

def test_build_and_parse_entries():
    assert snmp.build_location_entry('Rack 12') == {'Location': 'Rack 12'}
    assert snmp.build_contact_entry('noc', 'noc@example.net') == CONTACT
    assert snmp.parse_location_entry(LOCATION) == 'Rack 12, Example DC'
    assert snmp.parse_location_entry({}) is None
    assert snmp.parse_location_entry(None) is None
    assert snmp.parse_contact_entry(CONTACT) == NOC
    assert snmp.parse_contact_entry({}) is None
    assert snmp.parse_contact_entry(None) is None


@pytest.mark.parametrize('location', ('', '   '))
def test_validate_location_rejects_empty(location):
    with pytest.raises(ValueError) as excinfo:
        snmp.validate_location(location)
    assert 'location must not be empty' in str(excinfo.value)


@pytest.mark.parametrize('name,email,message', (
    ('', 'noc@example.net', 'contact name must not be empty'),
    ('noc', None, 'contact email is required when state=present'),
    ('noc', 'noc', '"noc" is not a valid e-mail address'),
    ('noc', 'noc@example', '"noc@example" is not a valid e-mail address'),
    ('noc', 'noc @example.net', '"noc @example.net" is not a valid e-mail address'),
))
def test_validate_contact_rejects(name, email, message):
    with pytest.raises(ValueError) as excinfo:
        snmp.validate_contact(name, email)
    assert str(excinfo.value) == message


def test_validate_contact_accepts_long_top_level_domains():
    snmp.validate_contact('noc', 'network.operations+sonic@example.network')


# -- module runs ------------------------------------------------------------------

@pytest.mark.parametrize('check_mode', (True, False))
def test_create_location_and_contact(fake_swsscommon, run_module, check_mode):
    result = run_module(snmp, dict(location='Rack 12, Example DC', contact=NOC), check_mode=check_mode)
    after = {'LOCATION': LOCATION, 'CONTACT': CONTACT}
    assert result['changed'] is True
    assert result['location'] == 'Rack 12, Example DC'
    assert result['contact'] == NOC
    assert result['diff'] == {'before': {}, 'after': after}
    if check_mode:
        assert fake_swsscommon.writes == []
        assert fake_swsscommon.get_table('SNMP') == {}
    else:
        assert fake_swsscommon.writes == [
            ('set_entry', 'SNMP', 'LOCATION', LOCATION),
            ('set_entry', 'SNMP', 'CONTACT', CONTACT),
        ]
        assert fake_swsscommon.get_table('SNMP') == after


@pytest.mark.parametrize('check_mode', (True, False))
def test_idempotent(fake_swsscommon, run_module, check_mode):
    before = seed(fake_swsscommon)
    result = run_module(snmp, dict(location='Rack 12, Example DC', contact=NOC), check_mode=check_mode)
    assert result['changed'] is False
    assert result['diff'] == {'before': before, 'after': before}
    assert result['location'] == 'Rack 12, Example DC'
    assert result['contact'] == NOC
    assert fake_swsscommon.writes == []


@pytest.mark.parametrize('check_mode', (True, False))
def test_update_location_leaves_contact_alone(fake_swsscommon, run_module, check_mode):
    before = seed(fake_swsscommon)
    result = run_module(snmp, dict(location='Rack 13, Example DC'), check_mode=check_mode)
    after = {'LOCATION': {'Location': 'Rack 13, Example DC'}, 'CONTACT': CONTACT}
    assert result['changed'] is True
    assert result['location'] == 'Rack 13, Example DC'
    assert result['contact'] == NOC
    assert result['diff'] == {'before': before, 'after': after}
    if check_mode:
        assert fake_swsscommon.writes == []
        assert fake_swsscommon.get_table('SNMP') == before
    else:
        assert fake_swsscommon.writes == [('set_entry', 'SNMP', 'LOCATION', {'Location': 'Rack 13, Example DC'})]
        assert fake_swsscommon.get_table('SNMP') == after


@pytest.mark.parametrize('check_mode', (True, False))
def test_rename_contact_replaces_the_field(fake_swsscommon, run_module, check_mode):
    before = seed(fake_swsscommon)
    ops = {'name': 'ops', 'email': 'ops@example.net'}
    result = run_module(snmp, dict(contact=ops), check_mode=check_mode)
    after = {'LOCATION': LOCATION, 'CONTACT': {'ops': 'ops@example.net'}}
    assert result['changed'] is True
    assert result['contact'] == ops
    assert result['location'] == 'Rack 12, Example DC'
    assert result['diff'] == {'before': before, 'after': after}
    if check_mode:
        assert fake_swsscommon.writes == []
    else:
        # The old contact name must not linger as a second field.
        assert fake_swsscommon.writes == [('set_entry', 'SNMP', 'CONTACT', {'ops': 'ops@example.net'})]
        assert fake_swsscommon.get_entry('SNMP', 'CONTACT') == {'ops': 'ops@example.net'}


def test_change_contact_email_only(fake_swsscommon, run_module):
    seed(fake_swsscommon)
    result = run_module(snmp, dict(contact={'name': 'noc', 'email': 'noc@example.org'}))
    assert result['changed'] is True
    assert fake_swsscommon.get_entry('SNMP', 'CONTACT') == {'noc': 'noc@example.org'}


@pytest.mark.parametrize('check_mode', (True, False))
def test_remove_location_only(fake_swsscommon, run_module, check_mode):
    before = seed(fake_swsscommon)
    result = run_module(snmp, dict(location='whatever', state='absent'), check_mode=check_mode)
    assert result['changed'] is True
    assert result['location'] is None
    assert result['contact'] == NOC
    assert result['diff'] == {'before': before, 'after': {'CONTACT': CONTACT}}
    if check_mode:
        assert fake_swsscommon.writes == []
        assert fake_swsscommon.get_table('SNMP') == before
    else:
        assert fake_swsscommon.writes == [('set_entry', 'SNMP', 'LOCATION', None)]
        assert fake_swsscommon.get_table('SNMP') == {'CONTACT': CONTACT}


@pytest.mark.parametrize('check_mode', (True, False))
def test_remove_contact_without_email(fake_swsscommon, run_module, check_mode):
    before = seed(fake_swsscommon)
    result = run_module(snmp, dict(contact={'name': 'someone-else'}, state='absent'), check_mode=check_mode)
    assert result['changed'] is True
    assert result['location'] == 'Rack 12, Example DC'
    assert result['contact'] is None
    assert result['diff'] == {'before': before, 'after': {'LOCATION': LOCATION}}
    if check_mode:
        assert fake_swsscommon.writes == []
    else:
        assert fake_swsscommon.writes == [('set_entry', 'SNMP', 'CONTACT', None)]
        assert not fake_swsscommon.has_entry('SNMP', 'CONTACT')


@pytest.mark.parametrize('check_mode', (True, False))
def test_remove_both(fake_swsscommon, run_module, check_mode):
    before = seed(fake_swsscommon)
    result = run_module(snmp, dict(location='x', contact={'name': 'x'}, state='absent'), check_mode=check_mode)
    assert result['changed'] is True
    assert result['location'] is None
    assert result['contact'] is None
    assert result['diff'] == {'before': before, 'after': {}}
    if not check_mode:
        assert fake_swsscommon.get_table('SNMP') == {}


@pytest.mark.parametrize('check_mode', (True, False))
def test_remove_when_absent_is_not_a_change(fake_swsscommon, run_module, check_mode):
    result = run_module(snmp, dict(location='x', contact={'name': 'x'}, state='absent'), check_mode=check_mode)
    assert result['changed'] is False
    assert result['location'] is None
    assert result['contact'] is None
    assert result['diff'] == {'before': {}, 'after': {}}
    assert fake_swsscommon.writes == []


@pytest.mark.parametrize('params,message', (
    (dict(location=''), 'location must not be empty; use state=absent to remove it'),
    (dict(contact={'name': 'noc'}), 'contact email is required when state=present'),
    (dict(contact={'name': 'noc', 'email': 'nobody'}), '"nobody" is not a valid e-mail address'),
    (dict(location='Rack 12', contact={'name': '', 'email': 'noc@example.net'}), 'contact name must not be empty'),
))
def test_invalid_input_fails_before_writing(fake_swsscommon, run_module, params, message):
    seed(fake_swsscommon)
    result = run_module(snmp, params, expect_failure=True)
    assert result['msg'] == message
    assert fake_swsscommon.writes == []


def test_requires_location_or_contact(fake_swsscommon, run_module):
    result = run_module(snmp, dict(state='absent'), expect_failure=True)
    assert 'one of the following is required' in result['msg']
    assert fake_swsscommon.writes == []
