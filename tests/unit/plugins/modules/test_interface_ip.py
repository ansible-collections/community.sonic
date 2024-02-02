# -*- coding: utf-8 -*-
# pylint: disable=disallowed-name

from __future__ import (absolute_import, division, print_function)
__metaclass__ = type

import ipaddress
from ansible_collections.community.sonic.plugins.modules import interface_ip


class fake_configdb:
    def __init__(self, tables):
        self._tables = tables

    def get_entry(self, table, key):
        return self._tables.get(table, {}).get(key, {})

    def set_entry(self, table, key, value):
        tv = self._tables.get(table, {})
        tv[key] = value
        self._tables[table] = tv

    def get_table(self, table):
        return self._tables.get(table, {})


def test_get_interface_table():
    table = interface_ip.get_interface_table('Ethernet0.12')
    assert table == 'VLAN_SUB_INTERFACE'

    table = interface_ip.get_interface_table('Vlan3600')
    assert table == 'VLAN_INTERFACE'

    table = interface_ip.get_interface_table('Ethernet12')
    assert table == 'INTERFACE'

    table = interface_ip.get_interface_table('PortChannel2')
    assert table == 'PORTCHANNEL_INTERFACE'

    table = interface_ip.get_interface_table('Loopback100')
    assert table == 'LOOPBACK_INTERFACE'

    table = interface_ip.get_interface_table('eth0')
    assert table is None


def test_is_vlan_member():
    tables = {
        'VLAN_MEMBER': {
            ('Vlan3600', 'Ethernet0'): {}
        },
    }
    cdb = fake_configdb(tables)

    is_member = interface_ip.is_vlan_member(cdb, 'Ethernet0')
    assert is_member

    is_member = interface_ip.is_vlan_member(cdb, 'Ethernet1')
    assert not is_member


def test_get_current_addresses():
    tables = {
        'VLAN_INTERFACE': {
            ('Vlan3600', '10.2.0.3/24'): {}
        }
    }
    test_addr = ipaddress.ip_interface('10.2.0.3/24')
    cdb = fake_configdb(tables)

    cur_addrs = interface_ip.get_current_addresses(cdb, 'VLAN_INTERFACE', 'Vlan3600')
    assert cur_addrs == set((test_addr,))

    cur_addrs = interface_ip.get_current_addresses(cdb, 'VLAN_INTERFACE', 'Vlan1')
    assert len(cur_addrs) == 0
