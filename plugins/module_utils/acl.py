# -*- coding: utf-8 -*-
#
# GNU General Public License v3.0+ (see https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

"""Shared pieces of the ``acl_table`` and ``acl_rule`` modules.

SONiC expresses a dual-stack data-plane ACL in one of two ways depending on
the ASIC: a single ``L3V4V6`` table (*combined*) or an ``L3`` table for IPv4
next to an ``L3V6`` table for IPv6 (*split*). Both modules need to know which
layout a policy uses, and both watch ``STATE_DB`` for the status orchagent
publishes after it has processed a table or rule. That logic lives here.

The helpers are plain functions so they can be unit tested without a device;
the two that touch the database take a :class:`~config_db.ConfigDB` instance.
"""

from __future__ import (absolute_import, division, print_function)
__metaclass__ = type

import time

from ansible_collections.community.sonic.plugins.module_utils.config_db import ConfigDBError, join_key


#: CONFIG_DB tables.
ACL_TABLE = 'ACL_TABLE'
ACL_RULE = 'ACL_RULE'

#: STATE_DB tables written by orchagent (``aclorch``).
STATE_ACL_TABLE_TABLE = 'ACL_TABLE_TABLE'
STATE_ACL_RULE_TABLE = 'ACL_RULE_TABLE'
STATE_ACL_STAGE_CAPABILITY_TABLE = 'ACL_STAGE_CAPABILITY_TABLE'

#: Field of ``ACL_STAGE_CAPABILITY_TABLE|<STAGE>`` that says whether ``L3V4V6`` tables work (recent releases only).
CAPABILITY_L3V4V6 = 'supported_L3V4V6'

#: Status values orchagent writes to the ``status`` field of the STATE_DB tables.
STATUS_ACTIVE = 'Active'
STATUS_INACTIVE = 'Inactive'

TYPE_L3 = 'L3'
TYPE_L3V6 = 'L3V6'
TYPE_L3V4V6 = 'L3V4V6'

#: Table types this collection knows about; other names are accepted for user-defined ``ACL_TABLE_TYPE`` entries.
KNOWN_TABLE_TYPES = (TYPE_L3, TYPE_L3V6, TYPE_L3V4V6, 'L2', 'MIRROR', 'MIRRORV6', 'MIRROR_DSCP', 'CTRLPLANE',
                     'PFCWD', 'DROP', 'MCLAG', 'MUX', 'DTEL_FLOW_WATCHLIST', 'DTEL_DROP_WATCHLIST')

FAMILY_COMBINED = 'combined'
FAMILY_SPLIT = 'split'
FAMILY_AUTO = 'auto'

DEFAULT_V6_SUFFIX = '_v6'

#: Patched by tests so waits do not take real time.
sleep = time.sleep
monotonic = time.monotonic


class AclError(ConfigDBError):
    """Raised for invalid ACL options or when orchagent rejects what was written."""


class AclStatusError(AclError):
    """Raised when STATE_DB reports a table or rule as ``Inactive`` or never reports it at all."""


def list_field(entry, field):
    """Return a list-typed field of an entry as a list, treating the ``['']`` an empty list reads back as as ``[]``."""
    return [v for v in (entry.get(field) or []) if v != '']


# ---------------------------------------------------------------------------
# Family layout
# ---------------------------------------------------------------------------

def v6_table_name(name, suffix=DEFAULT_V6_SUFFIX):
    """Return the name of the IPv6 half of a split policy: ``v6_table_name('BGP_CULL') == 'BGP_CULL_v6'``."""
    return '%s%s' % (name, suffix)


def layout_from_config(name, acl_tables, suffix=DEFAULT_V6_SUFFIX):
    """Work out how the policy ``name`` is laid out from the stored ``ACL_TABLE`` entries.

    Returns ``(family_mode, tables)`` where ``family_mode`` is ``combined``,
    ``split`` or ``None`` (single table of another type, or no table at all)
    and ``tables`` is ``{table_name: type}`` for the tables that belong to
    the policy, ``{}`` when none exist.

    * ``<name>`` of type ``L3V4V6`` is a combined policy.
    * ``<name>`` of type ``L3`` next to ``<name><suffix>`` of type ``L3V6`` is a split policy.
    * ``<name>`` of type ``L3`` on its own is treated as split with the IPv6
      half missing, so that a table whose IPv6 twin was lost is repaired
      rather than reported as a different layout.
    * Anything else is a single table and reported with ``family_mode=None``.
    """
    main = acl_tables.get(name)
    twin_name = v6_table_name(name, suffix)
    twin = acl_tables.get(twin_name)
    if main is None:
        if twin is not None and twin.get('type') == TYPE_L3V6:
            return FAMILY_SPLIT, {twin_name: TYPE_L3V6}
        return None, {}
    main_type = main.get('type')
    if main_type == TYPE_L3V4V6:
        return FAMILY_COMBINED, {name: TYPE_L3V4V6}
    if main_type == TYPE_L3:
        tables = {name: TYPE_L3}
        if twin is not None and twin.get('type') == TYPE_L3V6:
            tables[twin_name] = TYPE_L3V6
        return FAMILY_SPLIT, tables
    return None, {name: main_type}


def tables_for_mode(name, family_mode, suffix=DEFAULT_V6_SUFFIX):
    """Return ``{table_name: type}`` for a resolved family mode."""
    if family_mode == FAMILY_COMBINED:
        return {name: TYPE_L3V4V6}
    if family_mode == FAMILY_SPLIT:
        return {name: TYPE_L3, v6_table_name(name, suffix): TYPE_L3V6}
    raise AclError('unknown family_mode "%s"' % family_mode)


def capability_l3v4v6(state_db, stage):
    """Return ``True``/``False`` when STATE_DB publishes ``L3V4V6`` support for the stage, ``None`` when it does not.

    Recent orchagent versions write ``supported_L3V4V6`` into
    ``ACL_STAGE_CAPABILITY_TABLE|INGRESS`` and ``|EGRESS``; older releases do
    not, in which case the caller has to probe by creating a table.
    """
    entry = state_db.get_entry(STATE_ACL_STAGE_CAPABILITY_TABLE, stage.upper())
    value = entry.get(CAPABILITY_L3V4V6)
    if value is None:
        return None
    return str(value).strip().lower() == 'true'


# ---------------------------------------------------------------------------
# STATE_DB status
# ---------------------------------------------------------------------------
#
# orchagent writes ``status`` only after it has processed a CONFIG_DB write
# (``doAclTableTask``/``doAclRuleTask`` end every SET they finish with
# ``setAclTableStatus``/``setAclRuleStatus``, for updates of existing objects
# too, and every DEL with the matching remove). Until then STATE_DB holds the
# status of the previous configuration, which looks exactly like an answer to
# the new one. The modules therefore delete a key's status entry right before
# writing a change to it (:func:`clear_status`) and only accept a status that
# appeared afterwards: ``None`` keeps :func:`wait_for_status` polling, and an
# ``Active`` or ``Inactive`` it then sees is unambiguous.

def clear_status(state_db, table, keys):
    """Delete the STATE_DB status entries of ``keys`` that exist, so the next status seen is orchagent's answer to our write.

    Returns the keys that had an entry. Nothing is deleted in check mode
    (the wrapper skips writes), and keys without an entry are left alone so
    unchanged objects keep their status and need no wait.
    """
    cleared = []
    for key in keys:
        key = join_key(key)
        if state_db.get_entry(table, key):
            state_db.delete_entry(table, key)
            cleared.append(key)
    return cleared


def wait_for_status(state_db, table, keys, timeout):
    """Poll STATE_DB until every key in ``keys`` has ``status=Active`` or ``timeout`` seconds have passed.

    Returns ``{key: status}`` with the last status seen for each key
    (``None`` when orchagent never wrote an entry). Returns as soon as every
    key is ``Active`` or any key is ``Inactive``; the pending states keep
    the wait going until the deadline. A ``timeout`` of ``0`` reads the
    status once without waiting. Call :func:`clear_status` for the keys that
    were changed before writing them, otherwise the status of the previous
    configuration is returned.
    """
    keys = [join_key(k) for k in keys]
    deadline = monotonic() + max(timeout, 0)
    statuses = dict((k, None) for k in keys)
    while True:
        for key in keys:
            statuses[key] = state_db.get_entry(table, key).get('status')
        if all(s == STATUS_ACTIVE for s in statuses.values()):
            return statuses
        if any(s == STATUS_INACTIVE for s in statuses.values()):
            return statuses
        if monotonic() >= deadline:
            return statuses
        sleep(min(0.5, max(deadline - monotonic(), 0)))


def wait_for_removal(state_db, table, keys, timeout):
    """Poll STATE_DB until none of ``keys`` has an entry any more or ``timeout`` seconds have passed.

    orchagent deletes the status entry when it has processed the removal of
    a table or rule; a stale ``Inactive`` entry would otherwise be mistaken
    for the result of a following write to the same key.
    """
    keys = [join_key(k) for k in keys]
    deadline = monotonic() + max(timeout, 0)
    while True:
        if not any(state_db.get_entry(table, key) for key in keys):
            return True
        if monotonic() >= deadline:
            return False
        sleep(min(0.5, max(deadline - monotonic(), 0)))


def describe_failed_status(statuses, what, state_table):
    """Return an error message for :func:`wait_for_status` results that are not all ``Active``, or ``None``."""
    failed = sorted((k, s) for k, s in statuses.items() if s != STATUS_ACTIVE)
    if not failed:
        return None
    parts = ['%s: %s' % (key, status or 'no status reported') for key, status in failed]
    return ('orchagent did not accept %s (%s); see "show logging" for the reason and STATE_DB %s for the status'
            % (what, ', '.join(parts), state_table))


def check_status(state_db, table, keys, timeout, what):
    """Wait for the given STATE_DB keys to become ``Active`` and raise :class:`AclStatusError` otherwise.

    ``what`` names the objects in the error message ("ACL table BGP_CULL",
    "ACL rules in BGP_CULL"). A ``timeout`` of ``0`` (or ``None``) disables the check.
    """
    if not timeout or not keys:
        return {}
    statuses = wait_for_status(state_db, table, keys, timeout)
    message = describe_failed_status(statuses, what, table)
    if message:
        raise AclStatusError(message)
    return statuses
