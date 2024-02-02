# -*- coding: utf-8 -*-
# pylint: disable=disallowed-name

from __future__ import (absolute_import, division, print_function)
__metaclass__ = type

from ansible_collections.community.sonic.tests.unit.utils import fake_environment
from ansible_collections.community.sonic.plugins.modules import vlan


def test_check_address():
    is_addr6 = vlan.check_address('2002::1')
    assert is_addr6
    is_addr4 = vlan.check_address('127.0.1.2')
    assert is_addr4
    is_addr_bad = vlan.check_address('falafel')
    assert not is_addr_bad


def test_build_vlan_entry_present():
    key, val = vlan.build_vlan_entry(vlanid=3360, state='present', dhcp_servers=['127.0.0.1', '::1'])
    assert key == 'Vlan3360'
    assert val.get('vlanid') == 3360
    assert val.get('dhcp_servers') == ['127.0.0.1']
    assert val.get('dhcpv6_servers') == ['::1']


def test_build_vlan_entry_absent():
    key, val = vlan.build_vlan_entry(vlanid=3360, state='absent', dhcp_servers=['127.0.0.1', '::1'])
    assert key == 'Vlan3360'
    assert val is None


def test_vlan_add_and_remove():
    with fake_environment(vlan, db_tables=None, vlanid=3600, dhcp_servers=['127.0.0.1']) as env:
        vlan.run_module()
    assert not env.failed
    assert env.result['changed']
    assert env.result['interface'] == 'Vlan3600'
    entry = env.get_entry('VLAN', 'Vlan3600')
    assert entry['vlanid'] == 3600
    assert entry['dhcp_servers'] == ['127.0.0.1']

    db_tables = env.db_tables

    with fake_environment(vlan, db_tables=db_tables, vlanid=3600, state='absent') as env:
        vlan.run_module()
    assert not env.failed
    assert env.result['changed']
    assert env.result['interface'] == 'Vlan3600'
    assert not env.get_entry('VLAN', 'Vlan3600')


def test_vlan_check_mode():
    with fake_environment(vlan, db_tables=None, vlanid=3600, _ansible_check_mode=True) as env:
        vlan.run_module()
    assert not env.failed
    assert env.result['changed']
    assert not env.get_table('VLAN')


def test_vlan_no_change():
    db_tables = {
        'VLAN': {
            'Vlan3600': {
                'vlanid': 3600,
            },
        },
    }

    with fake_environment(vlan, db_tables=db_tables, vlanid=3600) as env:
        vlan.run_module()
    assert not env.failed
    assert not env.result['changed']
