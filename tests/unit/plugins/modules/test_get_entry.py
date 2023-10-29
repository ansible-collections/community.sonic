# -*- coding: utf-8 -*-
# pylint: disable=disallowed-name

from __future__ import (absolute_import, division, print_function)
__metaclass__ = type

from ansible_collections.community.sonic.plugins.modules import get_entry


def test_fix_keys():
    test_dict = {
        'not_tuple': 'falafel',
        ('is', 'tuple'): 'tahini',
    }
    new_dict = get_entry.fix_keys(test_dict)
    assert new_dict.get('not_tuple') == 'falafel'
    assert new_dict.get('is|tuple') == 'tahini'
    assert ('is', 'tuple') not in new_dict
