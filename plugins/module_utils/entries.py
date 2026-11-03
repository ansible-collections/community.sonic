# GNU General Public License v3.0+ (see https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

"""Compatibility shim: ``compare_entries`` now lives in ``module_utils.config_db``."""

from __future__ import (absolute_import, division, print_function)
__metaclass__ = type

from ansible_collections.community.sonic.plugins.module_utils.config_db import compare_entries  # noqa: F401  pylint: disable=unused-import

__all__ = ['compare_entries']
