# -*- coding: utf-8 -*-
# pylint: disable=disallowed-name

from __future__ import (absolute_import, division, print_function)
__metaclass__ = type

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
