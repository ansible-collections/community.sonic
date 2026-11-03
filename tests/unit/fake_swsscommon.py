# -*- coding: utf-8 -*-
#
# GNU General Public License v3.0+ (see https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

"""A dict-backed stand-in for ``swsscommon`` used by the unit tests.

The real ``ConfigDBConnector`` stores every value as a string (lists become
comma separated ``field@`` entries), returns ``{}`` for both missing and empty
entries, and returns tuple keys from ``get_table()`` for compound keys. The
fake mirrors these quirks so modules are tested against realistic behaviour
without a redis instance.

Seed the database with ``{table: {key: {field: value}}}`` and inspect
``FakeConfigDBConnector.writes`` (a list of ``(method, table, key, value)``
tuples) to assert on what a module wrote. Entry replacements go through the
fake ``RedisTransactioner``/``RedisCommand`` like on a real switch and are
logged as ``set_entry`` writes plus an entry in ``transactions``.
"""

from __future__ import (absolute_import, division, print_function)
__metaclass__ = type

import copy


class FakeConfigDBConnector(object):
    """Minimal ``swsscommon.ConfigDBConnector`` replacement backed by a dictionary.

    All instances created from one :class:`FakeSwssCommon` share the same
    store, so a module connecting to CONFIG_DB sees the seeded data.
    """

    def __init__(self, store=None, **kwargs):
        self.store = store if store is not None else {}
        self.writes = []
        self.transactions = []
        self.connected = False
        self.db_name = None

    # -- connection -----------------------------------------------------------

    def connect(self, wait_for_init=True, retry_on=False):
        self.connected = True
        self.db_name = 'CONFIG_DB'

    def db_connect(self, db_name, wait_for_init=False, retry_on=False):
        self.connected = True
        self.db_name = db_name

    # -- (de)serialisation, mirroring the real connector ------------------------

    @staticmethod
    def serialize_key(key):
        if isinstance(key, (tuple, list)):
            return '|'.join(key)
        return key

    @staticmethod
    def deserialize_key(key):
        if '|' in key:
            return tuple(key.split('|'))
        return key

    @staticmethod
    def typed_to_raw(data):
        if data is None:
            return None
        if data == {}:
            return {'NULL': 'NULL'}
        raw = {}
        for k, v in data.items():
            if isinstance(v, list):
                raw[k + '@'] = ','.join(str(i) for i in v)
            else:
                raw[k] = str(v)
        return raw

    @staticmethod
    def raw_to_typed(raw):
        if raw is None:
            return None
        typed = {}
        for k, v in raw.items():
            if k == 'NULL':
                continue
            if k.endswith('@'):
                typed[k[:-1]] = v.split(',') if v != '' else []
            else:
                typed[k] = v
        return typed

    # -- reads ---------------------------------------------------------------

    def _table(self, table):
        return self.store.setdefault(table, {})

    def get_entry(self, table, key):
        key = self.serialize_key(key)
        raw = self.store.get(table, {}).get(key)
        if raw is None:
            return {}
        return self.raw_to_typed(copy.deepcopy(raw))

    def get_keys(self, table, split=True):
        keys = list(self.store.get(table, {}).keys())
        if split:
            return [self.deserialize_key(k) for k in keys]
        return keys

    def get_table(self, table):
        result = {}
        for key, raw in self.store.get(table, {}).items():
            result[self.deserialize_key(key)] = self.raw_to_typed(copy.deepcopy(raw))
        return result

    def get_config(self):
        return dict((table, self.get_table(table)) for table in self.store)

    # -- writes ---------------------------------------------------------------

    def set_entry(self, table, key, data):
        key = self.serialize_key(key)
        self.writes.append(('set_entry', table, key, copy.deepcopy(data)))
        if data is None:
            self._table(table).pop(key, None)
            return
        self._table(table)[key] = self.typed_to_raw(data)

    def mod_entry(self, table, key, data):
        key = self.serialize_key(key)
        self.writes.append(('mod_entry', table, key, copy.deepcopy(data)))
        if data is None:
            self._table(table).pop(key, None)
            return
        entry = self._table(table).setdefault(key, {})
        entry.pop('NULL', None)
        entry.update(self.typed_to_raw(data) if data else {})
        if not entry:
            entry['NULL'] = 'NULL'

    def delete_table(self, table):
        self.writes.append(('delete_table', table, None, None))
        self.store.pop(table, None)

    # -- raw redis access, as used by ConfigDB._replace_entry_atomically ---------

    TABLE_NAME_SEPARATOR = '|'

    def get_redis_client(self, db_name):
        assert db_name == self.db_name, 'client requested for %s while connected to %s' % (db_name, self.db_name)
        return FakeRedisClient(self)


class FakeRedisClient(object):
    """Stand-in for the ``swsscommon.DBConnector`` a connector hands out; works on raw ``TABLE|key`` hashes."""

    def __init__(self, connector):
        self.connector = connector

    def _locate(self, hash_name):
        table, _sep, key = hash_name.partition(FakeConfigDBConnector.TABLE_NAME_SEPARATOR)
        return table, key

    def hgetall(self, hash_name):
        table, key = self._locate(hash_name)
        return copy.deepcopy(self.connector.store.get(table, {}).get(key, {}))

    def apply(self, commands):
        """Apply queued ``('HSET', hash, field, value)``/``('HDEL', hash, field)`` commands as one write."""
        touched = {}
        for command in commands:
            table, key = self._locate(command[1])
            entry = self.connector._table(table).setdefault(key, {})
            if command[0] == 'HSET':
                entry[command[2]] = command[3]
            elif command[0] == 'HDEL':
                entry.pop(command[2], None)
            else:
                raise AssertionError('unexpected command %r' % (command,))
            touched[(table, key)] = entry
        for (table, key), entry in touched.items():
            self.connector.writes.append(('set_entry', table, key, FakeConfigDBConnector.raw_to_typed(copy.deepcopy(entry))))
            self.connector.transactions.append((table, key, list(commands)))


class FakeRedisCommand(object):
    """Stand-in for ``swsscommon.RedisCommand``; only the formatters the wrapper uses."""

    def __init__(self):
        self.command = None

    def formatHSET(self, hash_name, field, value):  # pylint: disable=invalid-name
        self.command = ('HSET', hash_name, field, value)

    def formatHDEL(self, hash_name, field):  # pylint: disable=invalid-name
        self.command = ('HDEL', hash_name, field)


class FakeRedisTransactioner(object):
    """Stand-in for ``swsscommon.RedisTransactioner``: queues commands and applies them all in ``exec``."""

    def __init__(self, client):
        self.client = client
        self.queue = None

    def multi(self):
        self.queue = []

    def enqueue(self, command, expected_type):
        assert self.queue is not None, 'enqueue() before multi()'
        assert command.command is not None, 'enqueue() of an unformatted command'
        assert expected_type == 3, 'HSET/HDEL reply with an integer (type 3), got %r' % (expected_type,)
        self.queue.append(command.command)

    def _exec(self):  # SWIG renames the C++ ``exec()`` because it is a Python built-in
        commands, self.queue = self.queue, None
        self.client.apply(commands)
        return True


class FakeSwssCommon(object):
    """Replacement for the ``swsscommon.swsscommon`` module object.

    ``seed`` is ``{table: {key: entry}}`` using typed values (strings or lists),
    the same shape modules work with. Every ``ConfigDBConnector()`` call returns
    a connector bound to the shared store; the connectors are kept in
    ``connectors`` and the combined write log is available as ``writes``.
    """

    #: Transaction classes the wrapper looks up on the module object.
    RedisTransactioner = FakeRedisTransactioner
    RedisCommand = FakeRedisCommand

    def __init__(self, seed=None):
        self.store = {}
        self.connectors = []
        self.seed(seed or {})

    def ConfigDBConnector(self, **kwargs):  # pylint: disable=invalid-name
        connector = FakeConfigDBConnector(self.store, **kwargs)
        self.connectors.append(connector)
        return connector

    @property
    def writes(self):
        return [w for c in self.connectors for w in c.writes]

    @property
    def transactions(self):
        """``(table, key, commands)`` for every ``set_entry`` that went through a redis transaction."""
        return [t for c in self.connectors for t in c.transactions]

    def seed(self, data):
        """Load ``{table: {key: entry}}`` with typed values into the store, replacing existing entries."""
        for table, entries in data.items():
            for key, value in entries.items():
                self.store.setdefault(table, {})[FakeConfigDBConnector.serialize_key(key)] = \
                    FakeConfigDBConnector.typed_to_raw(value)
        return self

    def get_table(self, table):
        """Typed view of a table with string keys, for assertions in tests."""
        connector = FakeConfigDBConnector(self.store)
        return dict((connector.serialize_key(k), v) for k, v in connector.get_table(table).items())

    def get_entry(self, table, key):
        """Typed view of one entry (``{}`` when absent), for assertions in tests."""
        return FakeConfigDBConnector(self.store).get_entry(table, key)

    def has_entry(self, table, key):
        return FakeConfigDBConnector.serialize_key(key) in self.store.get(table, {})
