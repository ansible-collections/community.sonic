# -*- coding: utf-8 -*-
#
# GNU General Public License v3.0+ (see https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

"""Shared CONFIG_DB plumbing for community.sonic modules.

Every module in this collection talks to the SONiC configuration database
through the ``swsscommon`` Python bindings that ship with SONiC. This module
collects the pieces that would otherwise be duplicated in each module:

* the guarded ``swsscommon`` import and the matching ``missing_required_lib``
  failure (see :func:`fail_if_missing_swsscommon`),
* a thin :class:`ConfigDB` wrapper around ``ConfigDBConnector`` that knows
  about Ansible check mode, normalises compound keys and offers
  :meth:`ConfigDB.ensure_entry` for the common "make this entry look like X"
  pattern,
* helpers for compound keys, port alias resolution, interface classification,
  boolean-to-string conversion and the result/diff dictionary.

Typical use in a module::

    from ansible_collections.community.sonic.plugins.module_utils.config_db import (
        ConfigDB, ConfigDBError, bool_to_up_down)

    def run_module():
        module = AnsibleModule(argument_spec=..., supports_check_mode=True)
        db = ConfigDB(module).connect()
        try:
            key = db.resolve_port(module.params['interface'])
            change = db.ensure_entry('PORT', key, {'admin_status': bool_to_up_down(module.params['enabled'])},
                                     exclusive=False)
        except ConfigDBError as e:
            module.fail_json(msg=str(e))
        module.exit_json(**change.result(interface=key))

All CONFIG_DB values are strings (lists of strings for ``field@`` entries).
:func:`normalize_entry` converts Python values accordingly so comparisons
between the desired and the stored state are meaningful.
"""

from __future__ import (absolute_import, division, print_function)
__metaclass__ = type

import copy
import re
import traceback
from collections import namedtuple

from ansible.module_utils.basic import missing_required_lib
from ansible.module_utils.common.dict_transformations import recursive_diff

try:
    from swsscommon import swsscommon
except ImportError:
    HAS_SWSSCOMMON = False
    SWSSCOMMON_IMPORT_ERROR = traceback.format_exc()
    swsscommon = None
else:
    HAS_SWSSCOMMON = True
    SWSSCOMMON_IMPORT_ERROR = None

#: hiredis reply type of the integer ``HSET``/``HDEL`` return inside an ``EXEC`` reply (``REDIS_REPLY_INTEGER``).
REDIS_REPLY_INTEGER = 3


#: Separator used by SONiC for compound CONFIG_DB keys, for example ``Vlan100|Ethernet0``.
KEY_SEPARATOR = '|'

#: L3 (IP address bearing) table for each interface name prefix, see :func:`l3_interface_table`.
L3_INTERFACE_TABLES = {
    'Ethernet': 'INTERFACE',
    'PortChannel': 'PORTCHANNEL_INTERFACE',
    'Vlan': 'VLAN_INTERFACE',
    'Loopback': 'LOOPBACK_INTERFACE',
}

#: Table that defines an interface of each kind, see :func:`interface_table`.
INTERFACE_TABLES = {
    'Ethernet': 'PORT',
    'PortChannel': 'PORTCHANNEL',
    'Vlan': 'VLAN',
    'Loopback': 'LOOPBACK_INTERFACE',
}

_INTERFACE_RE = re.compile(r'^(Ethernet|PortChannel|Vlan|Loopback)(\d+)$')


class ConfigDBError(Exception):
    """Base class for errors raised by this module.

    Modules should catch this and turn it into ``module.fail_json(msg=str(e))``.
    """


class UnknownInterfaceError(ConfigDBError):
    """Raised when an interface name or alias does not exist on the device."""


class UnsupportedInterfaceError(ConfigDBError):
    """Raised when an interface name is not of a kind the helper understands."""


def fail_if_missing_swsscommon(module):
    """Fail the module with the standard ``missing_required_lib`` message if swsscommon is unavailable."""
    if not HAS_SWSSCOMMON:
        module.fail_json(
            msg=missing_required_lib('swsscommon'),
            exception=SWSSCOMMON_IMPORT_ERROR)


# ---------------------------------------------------------------------------
# Key helpers
# ---------------------------------------------------------------------------

def join_key(*parts):
    """Build a compound CONFIG_DB key: ``join_key('Vlan100', 'Ethernet0') == 'Vlan100|Ethernet0'``.

    A single tuple or list argument is also accepted, as returned by
    ``ConfigDBConnector.get_table()`` for compound keys.
    """
    if len(parts) == 1 and isinstance(parts[0], (tuple, list)):
        parts = parts[0]
    return KEY_SEPARATOR.join(str(p) for p in parts)


def split_key(key):
    """Split a compound CONFIG_DB key into its parts: ``split_key('Vlan100|Ethernet0') == ['Vlan100', 'Ethernet0']``."""
    if isinstance(key, (tuple, list)):
        return [str(p) for p in key]
    return str(key).split(KEY_SEPARATOR)


def normalize_table_keys(table):
    """Return a copy of a ``get_table()`` result with tuple keys joined into ``a|b`` strings.

    ``ConfigDBConnector.get_table()`` returns tuples for compound keys, which
    cannot be JSON encoded in module results.
    """
    if not isinstance(table, dict):
        return table
    return dict((join_key(k) if isinstance(k, tuple) else k, v) for k, v in table.items())


# ---------------------------------------------------------------------------
# Value helpers
# ---------------------------------------------------------------------------

def bool_to_up_down(value):
    """Map a boolean to the ``up``/``down`` strings used by ``admin_status`` style fields. ``None`` passes through."""
    if value is None:
        return None
    return 'up' if value else 'down'


def bool_to_true_false(value):
    """Map a boolean to the ``true``/``false`` strings used by fields such as ``fast_rate``. ``None`` passes through."""
    if value is None:
        return None
    return 'true' if value else 'false'


def bool_to_enabled_disabled(value):
    """Map a boolean to the ``enabled``/``disabled`` strings used by the FEATURE table. ``None`` passes through."""
    if value is None:
        return None
    return 'enabled' if value else 'disabled'


_TRUE_STRINGS = frozenset(('up', 'true', 'enabled', 'enable', 'yes', 'on', '1'))
_FALSE_STRINGS = frozenset(('down', 'false', 'disabled', 'disable', 'no', 'off', '0'))


def str_to_bool(value, default=None):
    """Interpret a CONFIG_DB string (``up``/``down``, ``true``/``false``, ``enabled``/``disabled``) as a boolean.

    Returns ``default`` for ``None`` or an unrecognised value.
    """
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in _TRUE_STRINGS:
        return True
    if text in _FALSE_STRINGS:
        return False
    return default


def normalize_value(value):
    """Convert a Python value to the representation CONFIG_DB stores.

    * ``bool`` becomes ``'true'``/``'false'`` (use the ``bool_to_*`` helpers for other vocabularies),
    * ``list``/``tuple`` become a list of strings (``field@`` entries),
    * everything else is passed through ``str()``.
    * ``None`` is returned unchanged; :func:`normalize_entry` treats it as "field absent".
    """
    if value is None:
        return None
    if isinstance(value, bool):
        return bool_to_true_false(value)
    if isinstance(value, (list, tuple)):
        return [str(v) for v in value]
    return str(value)


def normalize_entry(entry):
    """Normalise every field of an entry with :func:`normalize_value`, dropping fields whose value is ``None``.

    ``None`` entries (meaning "absent") are returned unchanged.
    """
    if entry is None:
        return None
    return dict((k, normalize_value(v)) for k, v in entry.items() if v is not None)


def compare_entries(new, cur):
    """Return ``True`` if two CONFIG_DB entries differ.

    Empty and ``None`` entries are treated as equal to each other (both mean
    "absent"). Kept for compatibility with ``module_utils.entries``.
    """
    if not new and not cur:
        return False
    if (not new) != (not cur):
        return True
    return recursive_diff(new, cur) is not None


# ---------------------------------------------------------------------------
# Interface helpers
# ---------------------------------------------------------------------------

def interface_kind(name):
    """Return the interface kind prefix (``Ethernet``, ``PortChannel``, ``Vlan`` or ``Loopback``) of a SONiC interface name.

    Raises :class:`UnsupportedInterfaceError` for any other name, including port aliases.
    """
    m = _INTERFACE_RE.match(str(name))
    if m is None:
        raise UnsupportedInterfaceError(
            'unsupported interface name "%s"; expected Ethernet*, PortChannel*, Vlan* or Loopback*' % name)
    return m.group(1)


def interface_table(name):
    """Return the table that defines the given interface: ``PORT``, ``PORTCHANNEL``, ``VLAN`` or ``LOOPBACK_INTERFACE``."""
    return INTERFACE_TABLES[interface_kind(name)]


def l3_interface_table(name):
    """Return the L3 table holding IP addresses and VRF binding for the given interface.

    ``Ethernet*`` maps to ``INTERFACE``, ``PortChannel*`` to ``PORTCHANNEL_INTERFACE``,
    ``Vlan*`` to ``VLAN_INTERFACE`` and ``Loopback*`` to ``LOOPBACK_INTERFACE``.
    """
    return L3_INTERFACE_TABLES[interface_kind(name)]


def port_alias_map(port_table):
    """Return an ``{alias: port}`` dictionary built from the ``alias`` field of a ``PORT`` table."""
    return dict((v['alias'], k) for k, v in port_table.items() if isinstance(v, dict) and 'alias' in v)


def resolve_port_name(port_table, name):
    """Resolve a port name or alias (``QSFP1``) against a ``PORT`` table and return the canonical ``EthernetN`` name.

    Raises :class:`UnknownInterfaceError` if neither a port nor an alias matches.
    """
    if name in port_table:
        return name
    resolved = port_alias_map(port_table).get(name)
    if resolved is None:
        raise UnknownInterfaceError('could not find interface "%s"' % name)
    return resolved


def resolve_interface_name(port_table, name):
    """Like :func:`resolve_port_name`, but pass well-formed ``PortChannel*``, ``Vlan*`` and ``Loopback*`` names through.

    Useful for options that accept any interface, such as VLAN or PortChannel
    membership, while still allowing port aliases for physical ports.
    """
    m = _INTERFACE_RE.match(str(name))
    if m is not None and m.group(1) != 'Ethernet':
        return name
    return resolve_port_name(port_table, name)


# ---------------------------------------------------------------------------
# Results
# ---------------------------------------------------------------------------

def build_result(changed, before, after, **extra):
    """Build the module result dictionary with the standard ``diff`` layout.

    ``before``/``after`` are the entry contents (``{}`` for an absent entry).
    Additional return values are passed as keyword arguments.
    """
    diff = {
        'before': before if before is not None else {},
        'after': after if after is not None else {},
    }
    result = dict(changed=bool(changed), diff=diff)
    result.update(extra)
    return result


class EntryChange(namedtuple('EntryChange', ('changed', 'before', 'after'))):
    """Outcome of :meth:`ConfigDB.ensure_entry`; unpacks as ``(changed, before, after)``.

    ``before`` and ``after`` are entry dictionaries, ``{}`` when the entry is absent.
    """

    __slots__ = ()

    @property
    def diff(self):
        """The ``{'before': ..., 'after': ...}`` dictionary for Ansible diff mode."""
        return {'before': self.before, 'after': self.after}

    def result(self, **extra):
        """Return the module result dictionary (``changed`` plus ``diff``) with extra return values merged in."""
        return build_result(self.changed, self.before, self.after, **extra)


# ---------------------------------------------------------------------------
# Database wrapper
# ---------------------------------------------------------------------------

class ConfigDB(object):
    """Thin wrapper around ``swsscommon.ConfigDBConnector`` for Ansible modules.

    * The constructor fails the module with a ``missing_required_lib`` message
      when swsscommon cannot be imported.
    * Reads return copies with compound keys joined into ``a|b`` strings.
    * **All write methods are no-ops in check mode**; modules can therefore be
      written straight-line and still report accurate ``changed``/``diff``.
    * ``db_name`` selects another SONiC database such as ``STATE_DB`` or
      ``APPL_DB`` (read-only use is recommended for anything but CONFIG_DB).

    Pass ``connector`` to supply a pre-built connector, mostly for tests.
    """

    def __init__(self, module, db_name='CONFIG_DB', connector=None):
        self.module = module
        self.db_name = db_name
        self._connector = connector
        self._port_table = None
        if connector is None:
            fail_if_missing_swsscommon(module)

    @property
    def check_mode(self):
        """True when the module runs in check mode and writes must be skipped."""
        return bool(getattr(self.module, 'check_mode', False))

    @property
    def connector(self):
        """The underlying ``ConfigDBConnector``; raises if :meth:`connect` has not been called."""
        if self._connector is None:
            raise ConfigDBError('ConfigDB.connect() has not been called')
        return self._connector

    def connect(self):
        """Connect to the database and return ``self`` so it can be chained."""
        if self._connector is None:
            self._connector = swsscommon.ConfigDBConnector()
        if self.db_name == 'CONFIG_DB':
            self._connector.connect()
        else:
            self._connector.db_connect(self.db_name)
        return self

    # -- reads -------------------------------------------------------------

    def get_table(self, table):
        """Return the whole table as ``{key: entry}`` with compound keys joined, ``{}`` if empty."""
        return normalize_table_keys(copy.deepcopy(self.connector.get_table(table) or {}))

    def get_keys(self, table):
        """Return the list of keys in a table, compound keys joined, ``[]`` if empty."""
        keys = self.connector.get_keys(table) or []
        return [join_key(k) if isinstance(k, (tuple, list)) else k for k in keys]

    def get_entry(self, table, key):
        """Return a copy of an entry, ``{}`` if it is absent or empty.

        SONiC stores empty entries (``PORTCHANNEL_MEMBER``, ``DNS_NAMESERVER``)
        as ``{}``, so use :meth:`has_entry` to distinguish "empty" from "absent".
        """
        return copy.deepcopy(self.connector.get_entry(table, join_key(key)) or {})

    def has_entry(self, table, key):
        """Return ``True`` if the key exists in the table, even with an empty value."""
        return join_key(key) in self.get_keys(table)

    def get_config(self):
        """Return the complete database as ``{table: {key: entry}}`` with compound keys joined."""
        config = self.connector.get_config() or {}
        return dict((t, normalize_table_keys(copy.deepcopy(entries))) for t, entries in config.items())

    # -- writes (skipped in check mode) --------------------------------------

    def set_entry(self, table, key, value):
        """Replace an entry with ``value`` (fields not in ``value`` are removed); ``None`` deletes the entry.

        The replacement is a single Redis transaction (see
        :meth:`_replace_entry_atomically`), so daemons watching the table see
        the old entry and then the new one, never a half-written mix.
        """
        if self.check_mode:
            return
        key = join_key(key)
        if value is None or not self._replace_entry_atomically(table, key, value):
            self.connector.set_entry(table, key, value)

    def _replace_entry_atomically(self, table, key, value):
        """Write ``value`` over the stored entry inside one ``MULTI``/``EXEC``; returns ``False`` if that is not possible.

        ``swsscommon``'s own ``set_entry`` issues an ``HSET`` of the new fields
        followed by one ``HDEL`` per removed field. Every command raises a
        keyspace event and SONiC daemons (orchagent, hostcfgd, ...) re-read the
        whole entry on each event, so they can evaluate an intermediate entry
        that still carries the removed fields and, for example, reject it as
        invalid before the final state arrives. Queueing the same commands in a
        transaction delivers the events only after ``EXEC``, when the entry is
        complete. Falls back (returns ``False``) when the bindings lack the
        transaction classes.
        """
        connector = self.connector
        if swsscommon is None or not all(hasattr(swsscommon, n) for n in ('RedisTransactioner', 'RedisCommand')):
            return False
        if not hasattr(connector, 'get_redis_client') or not hasattr(connector, 'typed_to_raw'):
            return False
        separator = getattr(connector, 'TABLE_NAME_SEPARATOR', '|')
        hash_name = '%s%s%s' % (table.upper(), separator, key)
        raw = connector.typed_to_raw(value)
        client = connector.get_redis_client(connector.db_name)
        original = dict(client.hgetall(hash_name) or {})
        removed = sorted(f for f in original if f not in raw)

        transaction = swsscommon.RedisTransactioner(client)
        transaction.multi()
        for field in sorted(raw):
            command = swsscommon.RedisCommand()
            command.formatHSET(hash_name, field, raw[field])
            transaction.enqueue(command, REDIS_REPLY_INTEGER)
        for field in removed:
            command = swsscommon.RedisCommand()
            command.formatHDEL(hash_name, field)
            transaction.enqueue(command, REDIS_REPLY_INTEGER)
        # SWIG prefixes Python built-in names, so RedisTransactioner::exec() is ``_exec`` in the bindings.
        execute = getattr(transaction, '_exec', None) or getattr(transaction, 'exec')
        if not execute():
            raise ConfigDBError('the transaction replacing %s %s was not executed by redis' % (table, key))
        return True

    def mod_entry(self, table, key, value):
        """Merge ``value`` into an entry, leaving other fields alone; ``None`` deletes the entry."""
        if self.check_mode:
            return
        self.connector.mod_entry(table, join_key(key), value)

    def delete_entry(self, table, key):
        """Delete an entry. Equivalent to ``set_entry(table, key, None)``."""
        self.set_entry(table, key, None)

    def delete_table(self, table):
        """Delete every entry of a table."""
        if self.check_mode:
            return
        self.connector.delete_table(table)

    # -- declarative helpers -------------------------------------------------

    def ensure_entry(self, table, key, desired, exclusive=True):
        """Make the entry look like ``desired`` and return an :class:`EntryChange`.

        ``desired`` is normalised with :func:`normalize_entry`: values become
        CONFIG_DB strings and fields set to ``None`` are treated as absent.

        * ``desired is None`` removes the entry (see :meth:`ensure_absent`).
        * ``exclusive=True`` (default) makes the stored entry exactly ``desired``;
          fields not listed are removed. Use this when the module owns the entry
          (``VLAN``, ``VLAN_MEMBER``).
        * ``exclusive=False`` merges ``desired`` into the existing entry; fields
          not listed are kept and ``None`` removes a field. Use this for entries
          that carry fields the module does not manage (``DEVICE_METADATA``,
          ``FEATURE``, ``PORT``).

        Nothing is written in check mode or when the entry already matches.
        An entry with an empty value (``{}``) is created when missing, which is
        how membership-style tables (``PORTCHANNEL_MEMBER``) are populated.
        """
        key = join_key(key)
        if desired is None:
            return self.ensure_absent(table, key)

        remove = set(k for k, v in desired.items() if v is None)
        desired = normalize_entry(desired)
        before = self.get_entry(table, key)
        if exclusive:
            after = dict(desired)
        else:
            after = dict((k, v) for k, v in before.items() if k not in remove)
            after.update(desired)
        exists = bool(before) or self.has_entry(table, key)
        changed = not exists or compare_entries(after, before)
        if not changed:
            return EntryChange(False, before, after)

        if exclusive:
            self.set_entry(table, key, after)
        else:
            removed = [k for k in before if k not in after]
            if removed:
                self.set_entry(table, key, after)
            else:
                self.mod_entry(table, key, desired)
        return EntryChange(True, before, after)

    def ensure_absent(self, table, key):
        """Delete the entry if it exists and return an :class:`EntryChange` (``after`` is ``{}``)."""
        key = join_key(key)
        before = self.get_entry(table, key)
        exists = bool(before) or self.has_entry(table, key)
        if not exists:
            return EntryChange(False, {}, {})
        self.delete_entry(table, key)
        return EntryChange(True, before, {})

    # -- interface helpers ---------------------------------------------------

    def port_table(self, refresh=False):
        """Return the ``PORT`` table, cached after the first read."""
        if self._port_table is None or refresh:
            self._port_table = self.get_table('PORT')
        return self._port_table

    def resolve_port(self, name):
        """Resolve a port name or alias to its canonical ``EthernetN`` name; see :func:`resolve_port_name`."""
        return resolve_port_name(self.port_table(), name)

    def resolve_interface(self, name):
        """Resolve a port alias, passing PortChannel/Vlan/Loopback names through; see :func:`resolve_interface_name`."""
        return resolve_interface_name(self.port_table(), name)
