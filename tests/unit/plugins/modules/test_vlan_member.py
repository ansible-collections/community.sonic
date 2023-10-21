# -*- coding: utf-8 -*-
# pylint: disable=disallowed-name

from __future__ import (absolute_import, division, print_function)
__metaclass__ = type

from ansible_collections.community.sonic.plugins.modules import vlan_member


def test_build_vlan_member_entry_present():
    key, val = vlan_member.build_vlan_member_entry(vlanid=3360, interface='Ethernet90', state='present', tagged=True)
    assert key == 'Vlan3360|Ethernet90'
    assert val['tagging_mode'] == 'tagged'

    key, val = vlan_member.build_vlan_member_entry(vlanid=3360, interface='Ethernet90', state='present', tagged=False)
    assert key == 'Vlan3360|Ethernet90'
    assert val['tagging_mode'] == 'untagged'


def test_build_vlan_member_entry_absent():
    key, val = vlan_member.build_vlan_member_entry(vlanid=3360, interface='Ethernet90', state='absent', tagged=None)
    assert key == 'Vlan3360|Ethernet90'
    assert val is None
