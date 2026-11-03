# -*- coding: utf-8 -*-
# pylint: disable=disallowed-name
#
# GNU General Public License v3.0+ (see https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import (absolute_import, division, print_function)
__metaclass__ = type

from types import SimpleNamespace

import pytest

from ansible_collections.community.sonic.plugins.module_utils import config_db
from ansible_collections.community.sonic.plugins.module_utils.config_db import (
    ConfigDB,
    ConfigDBError,
    EntryChange,
    UnknownInterfaceError,
    UnsupportedInterfaceError,
    bool_to_enabled_disabled,
    bool_to_true_false,
    bool_to_up_down,
    build_result,
    compare_entries,
    interface_kind,
    interface_table,
    join_key,
    l3_interface_table,
    normalize_entry,
    normalize_table_keys,
    normalize_value,
    resolve_interface_name,
    resolve_port_name,
    split_key,
    str_to_bool,
)


PORT_TABLE = {
    'Ethernet0': {'alias': 'QSFP1', 'speed': '100000'},
    'Ethernet4': {'alias': 'QSFP2', 'speed': '100000'},
    'Ethernet8': {'speed': '100000'},
}


class FakeModule(SimpleNamespace):
    """Just enough of AnsibleModule for ConfigDB."""

    def __init__(self, check_mode=False):
        super(FakeModule, self).__init__(check_mode=check_mode, failures=[])

    def fail_json(self, **kwargs):
        self.failures.append(kwargs)
        raise RuntimeError(kwargs.get('msg'))


def connect(fake_swsscommon, check_mode=False, db_name='CONFIG_DB'):
    return ConfigDB(FakeModule(check_mode=check_mode), db_name=db_name).connect()


# -- key helpers -------------------------------------------------------------

def test_join_and_split_key():
    assert join_key('Vlan100', 'Ethernet0') == 'Vlan100|Ethernet0'
    assert join_key(('Vlan100', 'Ethernet0')) == 'Vlan100|Ethernet0'
    assert join_key('Vlan100') == 'Vlan100'
    assert join_key('eth0', '2001:db8::1/64') == 'eth0|2001:db8::1/64'
    assert split_key('Vlan100|Ethernet0') == ['Vlan100', 'Ethernet0']
    assert split_key(('Vlan100', 'Ethernet0')) == ['Vlan100', 'Ethernet0']
    assert split_key('Vlan100') == ['Vlan100']


def test_normalize_table_keys():
    table = {'plain': {'a': '1'}, ('is', 'tuple'): {'b': '2'}}
    assert normalize_table_keys(table) == {'plain': {'a': '1'}, 'is|tuple': {'b': '2'}}
    assert normalize_table_keys(None) is None


# -- value helpers -----------------------------------------------------------

def test_bool_helpers():
    assert bool_to_up_down(True) == 'up' and bool_to_up_down(False) == 'down' and bool_to_up_down(None) is None
    assert bool_to_true_false(True) == 'true' and bool_to_true_false(False) == 'false'
    assert bool_to_enabled_disabled(True) == 'enabled' and bool_to_enabled_disabled(False) == 'disabled'
    assert str_to_bool('up') is True and str_to_bool('down') is False
    assert str_to_bool('True') is True and str_to_bool('false') is False
    assert str_to_bool('enabled') is True and str_to_bool('disabled') is False
    assert str_to_bool(None) is None and str_to_bool('maybe', default=False) is False
    assert str_to_bool(True) is True


def test_normalize_value_and_entry():
    assert normalize_value(42) == '42'
    assert normalize_value(True) == 'true'
    assert normalize_value(['a', 1]) == ['a', '1']
    assert normalize_value(None) is None
    assert normalize_entry({'vlanid': 42, 'servers': ['10.0.0.1'], 'gone': None, 'flag': False}) == {
        'vlanid': '42', 'servers': ['10.0.0.1'], 'flag': 'false'}
    assert normalize_entry(None) is None
    assert normalize_entry({}) == {}


def test_compare_entries_reexported():
    from ansible_collections.community.sonic.plugins.module_utils.entries import compare_entries as legacy
    assert legacy is compare_entries
    assert compare_entries({'a': '1'}, {'a': '2'})
    assert not compare_entries({}, None)


# -- interface helpers ---------------------------------------------------------

@pytest.mark.parametrize('name,kind,table,l3_table', (
    ('Ethernet0', 'Ethernet', 'PORT', 'INTERFACE'),
    ('Ethernet128', 'Ethernet', 'PORT', 'INTERFACE'),
    ('PortChannel3', 'PortChannel', 'PORTCHANNEL', 'PORTCHANNEL_INTERFACE'),
    ('Vlan100', 'Vlan', 'VLAN', 'VLAN_INTERFACE'),
    ('Loopback0', 'Loopback', 'LOOPBACK_INTERFACE', 'LOOPBACK_INTERFACE'),
))
def test_interface_classification(name, kind, table, l3_table):
    assert interface_kind(name) == kind
    assert interface_table(name) == table
    assert l3_interface_table(name) == l3_table


@pytest.mark.parametrize('name', ('eth0', 'QSFP1', 'Ethernet', 'Vlan', 'Ethernet0.100', 'ethernet0', ''))
def test_interface_classification_rejects_unknown(name):
    with pytest.raises(UnsupportedInterfaceError):
        interface_kind(name)
    with pytest.raises(ConfigDBError):
        l3_interface_table(name)


def test_resolve_port_name():
    assert resolve_port_name(PORT_TABLE, 'Ethernet0') == 'Ethernet0'
    assert resolve_port_name(PORT_TABLE, 'QSFP2') == 'Ethernet4'
    assert resolve_port_name(PORT_TABLE, 'Ethernet8') == 'Ethernet8'
    with pytest.raises(UnknownInterfaceError, match='could not find interface "QSFP9"'):
        resolve_port_name(PORT_TABLE, 'QSFP9')
    with pytest.raises(UnknownInterfaceError):
        resolve_port_name(PORT_TABLE, 'Ethernet12')


def test_resolve_interface_name():
    assert resolve_interface_name(PORT_TABLE, 'QSFP1') == 'Ethernet0'
    assert resolve_interface_name(PORT_TABLE, 'PortChannel3') == 'PortChannel3'
    assert resolve_interface_name(PORT_TABLE, 'Vlan100') == 'Vlan100'
    with pytest.raises(UnknownInterfaceError):
        resolve_interface_name(PORT_TABLE, 'eth0')


# -- results -------------------------------------------------------------------

def test_build_result_and_entry_change():
    assert build_result(True, None, {'a': '1'}, interface='Ethernet0') == {
        'changed': True, 'diff': {'before': {}, 'after': {'a': '1'}}, 'interface': 'Ethernet0'}
    change = EntryChange(False, {'a': '1'}, {'a': '1'})
    changed, before, after = change
    assert (changed, before, after) == (False, {'a': '1'}, {'a': '1'})
    assert change.diff == {'before': {'a': '1'}, 'after': {'a': '1'}}
    assert change.result(key='x') == {'changed': False, 'diff': change.diff, 'key': 'x'}


# -- ConfigDB wrapper --------------------------------------------------------------

def test_missing_swsscommon_fails_module(monkeypatch):
    monkeypatch.setattr(config_db, 'HAS_SWSSCOMMON', False)
    monkeypatch.setattr(config_db, 'SWSSCOMMON_IMPORT_ERROR', 'Traceback: boom')
    module = FakeModule()
    with pytest.raises(RuntimeError):
        ConfigDB(module)
    assert len(module.failures) == 1
    assert 'swsscommon' in module.failures[0]['msg']
    assert module.failures[0]['exception'] == 'Traceback: boom'


def test_connect_and_reads(fake_swsscommon):
    fake_swsscommon.seed({
        'PORT': PORT_TABLE,
        'VLAN_MEMBER': {'Vlan100|Ethernet0': {'tagging_mode': 'tagged'}},
        'PORTCHANNEL_MEMBER': {'PortChannel3|Ethernet4': {}},
    })
    db = connect(fake_swsscommon)
    assert fake_swsscommon.connectors[0].connected
    assert fake_swsscommon.connectors[0].db_name == 'CONFIG_DB'
    assert db.get_table('VLAN_MEMBER') == {'Vlan100|Ethernet0': {'tagging_mode': 'tagged'}}
    assert db.get_keys('VLAN_MEMBER') == ['Vlan100|Ethernet0']
    assert db.get_entry('VLAN_MEMBER', 'Vlan100|Ethernet0') == {'tagging_mode': 'tagged'}
    assert db.get_entry('VLAN_MEMBER', ('Vlan100', 'Ethernet0')) == {'tagging_mode': 'tagged'}
    assert db.get_entry('VLAN_MEMBER', 'Vlan200|Ethernet0') == {}
    assert db.get_entry('PORTCHANNEL_MEMBER', 'PortChannel3|Ethernet4') == {}
    assert db.has_entry('PORTCHANNEL_MEMBER', 'PortChannel3|Ethernet4')
    assert not db.has_entry('PORTCHANNEL_MEMBER', 'PortChannel3|Ethernet0')
    assert db.get_table('NO_SUCH_TABLE') == {}
    assert db.get_config()['VLAN_MEMBER'] == {'Vlan100|Ethernet0': {'tagging_mode': 'tagged'}}
    # Reads are copies: mutating them must not leak into the store
    db.get_table('PORT')['Ethernet0']['speed'] = '1'
    assert db.get_entry('PORT', 'Ethernet0')['speed'] == '100000'


def test_connect_other_database(fake_swsscommon):
    db = connect(fake_swsscommon, db_name='STATE_DB')
    assert fake_swsscommon.connectors[0].db_name == 'STATE_DB'
    assert db.db_name == 'STATE_DB'


def test_connector_requires_connect(fake_swsscommon):
    db = ConfigDB(FakeModule())
    with pytest.raises(ConfigDBError):
        db.get_table('PORT')


def test_port_resolution(fake_swsscommon):
    fake_swsscommon.seed({'PORT': PORT_TABLE})
    db = connect(fake_swsscommon)
    assert db.resolve_port('QSFP1') == 'Ethernet0'
    assert db.resolve_interface('PortChannel1') == 'PortChannel1'
    assert db.resolve_interface('QSFP2') == 'Ethernet4'
    with pytest.raises(UnknownInterfaceError):
        db.resolve_port('QSFP9')
    # The PORT table is cached unless a refresh is requested
    fake_swsscommon.seed({'PORT': {'Ethernet12': {'alias': 'QSFP9'}}})
    with pytest.raises(UnknownInterfaceError):
        db.resolve_port('QSFP9')
    assert 'Ethernet12' in db.port_table(refresh=True)
    assert db.resolve_port('QSFP9') == 'Ethernet12'


@pytest.mark.parametrize('check_mode', (False, True))
def test_writes_honour_check_mode(fake_swsscommon, check_mode):
    fake_swsscommon.seed({'VLAN': {'Vlan100': {'vlanid': '100'}}})
    db = connect(fake_swsscommon, check_mode=check_mode)
    db.set_entry('VLAN', 'Vlan200', {'vlanid': '200'})
    db.mod_entry('VLAN', 'Vlan100', {'description': 'x'})
    db.delete_entry('VLAN', 'Vlan100')
    db.delete_table('VLAN')
    if check_mode:
        assert fake_swsscommon.writes == []
        assert fake_swsscommon.get_table('VLAN') == {'Vlan100': {'vlanid': '100'}}
    else:
        assert [w[0] for w in fake_swsscommon.writes] == ['set_entry', 'mod_entry', 'set_entry', 'delete_table']
        assert fake_swsscommon.writes[2] == ('set_entry', 'VLAN', 'Vlan100', None)
        assert fake_swsscommon.get_table('VLAN') == {}


def test_set_entry_replaces_in_one_transaction(fake_swsscommon):
    """Removed fields are HDELed and new ones HSET in the same MULTI/EXEC, so watchers never see a mix."""
    fake_swsscommon.seed({'ACL_RULE': {'T|R': {'PRIORITY': '5', 'DSCP': '46', 'PACKET_ACTION': 'DROP'}}})
    db = connect(fake_swsscommon)
    db.set_entry('ACL_RULE', ('T', 'R'), {'PRIORITY': '5', 'IP_PROTOCOL': '17', 'PACKET_ACTION': 'DROP'})
    assert fake_swsscommon.get_entry('ACL_RULE', 'T|R') == {'PRIORITY': '5', 'IP_PROTOCOL': '17', 'PACKET_ACTION': 'DROP'}
    assert fake_swsscommon.transactions == [('ACL_RULE', 'T|R', [
        ('HSET', 'ACL_RULE|T|R', 'IP_PROTOCOL', '17'),
        ('HSET', 'ACL_RULE|T|R', 'PACKET_ACTION', 'DROP'),
        ('HSET', 'ACL_RULE|T|R', 'PRIORITY', '5'),
        ('HDEL', 'ACL_RULE|T|R', 'DSCP'),
    ])]
    assert fake_swsscommon.writes == [('set_entry', 'ACL_RULE', 'T|R',
                                       {'PRIORITY': '5', 'IP_PROTOCOL': '17', 'PACKET_ACTION': 'DROP'})]


def test_set_entry_transaction_handles_lists_and_empty_entries(fake_swsscommon):
    fake_swsscommon.seed({'PORTCHANNEL_MEMBER': {'PortChannel1|Ethernet0': {}}})
    db = connect(fake_swsscommon)
    db.set_entry('VLAN', 'Vlan42', {'vlanid': '42', 'dhcp_servers': ['10.0.0.1', '10.0.0.2']})
    assert fake_swsscommon.get_entry('VLAN', 'Vlan42') == {'vlanid': '42', 'dhcp_servers': ['10.0.0.1', '10.0.0.2']}
    assert fake_swsscommon.transactions[-1][2] == [
        ('HSET', 'VLAN|Vlan42', 'dhcp_servers@', '10.0.0.1,10.0.0.2'),
        ('HSET', 'VLAN|Vlan42', 'vlanid', '42'),
    ]
    # An empty entry is stored as NULL:NULL and the placeholder goes away when real fields arrive.
    db.set_entry('PORTCHANNEL_MEMBER', 'PortChannel1|Ethernet0', {'x': '1'})
    assert fake_swsscommon.transactions[-1][2] == [
        ('HSET', 'PORTCHANNEL_MEMBER|PortChannel1|Ethernet0', 'x', '1'),
        ('HDEL', 'PORTCHANNEL_MEMBER|PortChannel1|Ethernet0', 'NULL'),
    ]
    db.set_entry('PORTCHANNEL_MEMBER', 'PortChannel1|Ethernet0', {})
    assert fake_swsscommon.transactions[-1][2] == [
        ('HSET', 'PORTCHANNEL_MEMBER|PortChannel1|Ethernet0', 'NULL', 'NULL'),
        ('HDEL', 'PORTCHANNEL_MEMBER|PortChannel1|Ethernet0', 'x'),
    ]
    assert fake_swsscommon.has_entry('PORTCHANNEL_MEMBER', 'PortChannel1|Ethernet0')
    assert fake_swsscommon.get_entry('PORTCHANNEL_MEMBER', 'PortChannel1|Ethernet0') == {}


def test_set_entry_delete_and_fallback_use_the_connector(fake_swsscommon, monkeypatch):
    fake_swsscommon.seed({'VLAN': {'Vlan42': {'vlanid': '42'}}})
    db = connect(fake_swsscommon)
    db.set_entry('VLAN', 'Vlan42', None)
    assert fake_swsscommon.writes == [('set_entry', 'VLAN', 'Vlan42', None)]
    assert fake_swsscommon.transactions == []
    # Bindings without RedisTransactioner fall back to the connector's own set_entry.
    monkeypatch.delattr(type(fake_swsscommon), 'RedisTransactioner')
    db.set_entry('VLAN', 'Vlan43', {'vlanid': '43'})
    assert fake_swsscommon.writes[-1] == ('set_entry', 'VLAN', 'Vlan43', {'vlanid': '43'})
    assert fake_swsscommon.transactions == []
    assert fake_swsscommon.get_entry('VLAN', 'Vlan43') == {'vlanid': '43'}


def test_set_entry_failed_transaction_raises(fake_swsscommon, monkeypatch):
    db = connect(fake_swsscommon)
    monkeypatch.setattr(fake_swsscommon.RedisTransactioner, '_exec', lambda self: False)
    with pytest.raises(config_db.ConfigDBError, match='transaction replacing VLAN Vlan1'):
        db.set_entry('VLAN', 'Vlan1', {'vlanid': '1'})


def test_ensure_entry_exclusive_create(fake_swsscommon):
    db = connect(fake_swsscommon)
    change = db.ensure_entry('VLAN', 'Vlan42', {'vlanid': 42, 'dhcp_servers': ['10.0.0.1']})
    assert change == (True, {}, {'vlanid': '42', 'dhcp_servers': ['10.0.0.1']})
    assert fake_swsscommon.writes == [('set_entry', 'VLAN', 'Vlan42', {'vlanid': '42', 'dhcp_servers': ['10.0.0.1']})]
    assert fake_swsscommon.get_entry('VLAN', 'Vlan42') == {'vlanid': '42', 'dhcp_servers': ['10.0.0.1']}


def test_ensure_entry_exclusive_idempotent_with_typed_values(fake_swsscommon):
    fake_swsscommon.seed({'VLAN': {'Vlan42': {'vlanid': '42'}}})
    db = connect(fake_swsscommon)
    change = db.ensure_entry('VLAN', 'Vlan42', {'vlanid': 42})
    assert change.changed is False
    assert change.before == change.after == {'vlanid': '42'}
    assert fake_swsscommon.writes == []


def test_ensure_entry_exclusive_removes_unlisted_fields(fake_swsscommon):
    fake_swsscommon.seed({'VLAN': {'Vlan42': {'vlanid': '42', 'dhcp_servers': ['10.0.0.1']}}})
    db = connect(fake_swsscommon)
    change = db.ensure_entry('VLAN', 'Vlan42', {'vlanid': '42'})
    assert change == (True, {'vlanid': '42', 'dhcp_servers': ['10.0.0.1']}, {'vlanid': '42'})
    assert fake_swsscommon.get_entry('VLAN', 'Vlan42') == {'vlanid': '42'}


def test_ensure_entry_exclusive_check_mode(fake_swsscommon):
    fake_swsscommon.seed({'VLAN': {'Vlan42': {'vlanid': '42'}}})
    db = connect(fake_swsscommon, check_mode=True)
    change = db.ensure_entry('VLAN', 'Vlan42', {'vlanid': '42', 'dhcp_servers': ['10.0.0.1']})
    assert change.changed is True
    assert change.diff == {'before': {'vlanid': '42'}, 'after': {'vlanid': '42', 'dhcp_servers': ['10.0.0.1']}}
    assert fake_swsscommon.writes == []
    assert fake_swsscommon.get_entry('VLAN', 'Vlan42') == {'vlanid': '42'}


def test_ensure_entry_merge_keeps_other_fields(fake_swsscommon):
    fake_swsscommon.seed({'DEVICE_METADATA': {'localhost': {'hostname': 'old', 'hwsku': 'SKU', 'platform': 'x86'}}})
    db = connect(fake_swsscommon)
    change = db.ensure_entry('DEVICE_METADATA', 'localhost', {'hostname': 'new', 'timezone': 'UTC'}, exclusive=False)
    assert change.changed
    assert change.before == {'hostname': 'old', 'hwsku': 'SKU', 'platform': 'x86'}
    assert change.after == {'hostname': 'new', 'hwsku': 'SKU', 'platform': 'x86', 'timezone': 'UTC'}
    # Only the managed fields are written, through mod_entry
    assert fake_swsscommon.writes == [('mod_entry', 'DEVICE_METADATA', 'localhost', {'hostname': 'new', 'timezone': 'UTC'})]
    assert fake_swsscommon.get_entry('DEVICE_METADATA', 'localhost') == change.after


def test_ensure_entry_merge_idempotent(fake_swsscommon):
    fake_swsscommon.seed({'FEATURE': {'sflow': {'state': 'enabled', 'auto_restart': 'enabled', 'delayed': 'False'}}})
    db = connect(fake_swsscommon)
    change = db.ensure_entry('FEATURE', 'sflow', {'state': 'enabled'}, exclusive=False)
    assert change.changed is False
    assert fake_swsscommon.writes == []


def test_ensure_entry_merge_none_removes_field(fake_swsscommon):
    fake_swsscommon.seed({'PORT': {'Ethernet0': {'alias': 'QSFP1', 'speed': '100000', 'fec': 'rs'}}})
    db = connect(fake_swsscommon)
    change = db.ensure_entry('PORT', 'Ethernet0', {'fec': None, 'speed': '40000'}, exclusive=False)
    assert change == (True, {'alias': 'QSFP1', 'speed': '100000', 'fec': 'rs'}, {'alias': 'QSFP1', 'speed': '40000'})
    # Removing a field needs the whole entry rewritten, as mod_entry cannot delete fields
    assert fake_swsscommon.writes == [('set_entry', 'PORT', 'Ethernet0', {'alias': 'QSFP1', 'speed': '40000'})]
    assert fake_swsscommon.get_entry('PORT', 'Ethernet0') == {'alias': 'QSFP1', 'speed': '40000'}


def test_ensure_entry_merge_none_for_absent_field_is_noop(fake_swsscommon):
    fake_swsscommon.seed({'PORT': {'Ethernet0': {'alias': 'QSFP1'}}})
    db = connect(fake_swsscommon)
    change = db.ensure_entry('PORT', 'Ethernet0', {'fec': None}, exclusive=False)
    assert change.changed is False
    assert fake_swsscommon.writes == []


def test_ensure_entry_merge_creates_missing_entry(fake_swsscommon):
    db = connect(fake_swsscommon)
    change = db.ensure_entry('SFLOW', 'global', {'admin_state': 'up'}, exclusive=False)
    assert change == (True, {}, {'admin_state': 'up'})
    assert fake_swsscommon.writes == [('mod_entry', 'SFLOW', 'global', {'admin_state': 'up'})]


def test_ensure_entry_empty_value_entries(fake_swsscommon):
    """Membership tables store {} values; presence must be detected by key, not by value."""
    db = connect(fake_swsscommon)
    key = ('PortChannel3', 'Ethernet0')
    change = db.ensure_entry('PORTCHANNEL_MEMBER', key, {})
    assert change == (True, {}, {})
    assert fake_swsscommon.writes == [('set_entry', 'PORTCHANNEL_MEMBER', 'PortChannel3|Ethernet0', {})]
    assert fake_swsscommon.has_entry('PORTCHANNEL_MEMBER', 'PortChannel3|Ethernet0')

    again = db.ensure_entry('PORTCHANNEL_MEMBER', 'PortChannel3|Ethernet0', {})
    assert again.changed is False
    assert len(fake_swsscommon.writes) == 1

    removed = db.ensure_entry('PORTCHANNEL_MEMBER', key, None)
    assert removed == (True, {}, {})
    assert not fake_swsscommon.has_entry('PORTCHANNEL_MEMBER', 'PortChannel3|Ethernet0')
    assert db.ensure_absent('PORTCHANNEL_MEMBER', key).changed is False


@pytest.mark.parametrize('check_mode', (False, True))
def test_ensure_absent(fake_swsscommon, check_mode):
    fake_swsscommon.seed({'VLAN_MEMBER': {'Vlan42|Ethernet0': {'tagging_mode': 'tagged'}}})
    db = connect(fake_swsscommon, check_mode=check_mode)
    change = db.ensure_absent('VLAN_MEMBER', 'Vlan42|Ethernet0')
    assert change == (True, {'tagging_mode': 'tagged'}, {})
    assert fake_swsscommon.has_entry('VLAN_MEMBER', 'Vlan42|Ethernet0') is check_mode
    if not check_mode:
        assert fake_swsscommon.writes == [('set_entry', 'VLAN_MEMBER', 'Vlan42|Ethernet0', None)]
        assert db.ensure_absent('VLAN_MEMBER', 'Vlan42|Ethernet0') == (False, {}, {})
