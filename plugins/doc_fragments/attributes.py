# -*- coding: utf-8 -*-

# Copyright (c) Ansible Project
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import (absolute_import, division, print_function)
__metaclass__ = type


class ModuleDocFragment(object):

    # Standard documentation fragment
    DOCUMENTATION = r'''
options: {}
attributes:
    check_mode:
      description: Can run in C(check_mode) and return changed status prediction without modifying target.
    diff_mode:
      description: Will return details on what has changed (or possibly needs changing in C(check_mode)), when in diff mode.
'''
