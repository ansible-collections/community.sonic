# -*- coding: utf-8 -*-

from __future__ import (absolute_import, division, print_function)
__metaclass__ = type

import pytest

from ansible_collections.community.sonic.plugins.modules import sonic_interface_port


PORT_TABLE = {
    'Ethernet0': {
        'alias': 'qsfp1',
    }
}


def test_set_description_by_alias():
    _, new_state, _, changed = sonic_interface_port.mutate_state(
        PORT_TABLE, interface='qsfp1', description='foobar')
    assert changed, 'state was expected to change'
    assert new_state['description'] == 'foobar'


# Test clearing both by unsetting the field and by setting an empty string
@pytest.mark.parametrize('value', (None, ''))
def test_clear_description_by_alias(value):
    port_table = PORT_TABLE
    port_table['Ethernet0']['description'] = 'foobar'
    _, new_state, _, changed = sonic_interface_port.mutate_state(
        PORT_TABLE, interface='qsfp1', description=value)
    assert changed, 'state was expected to change'
    assert 'description' not in new_state
