# GNU General Public License v3.0+ (see https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from ansible_collections.community.sonic.plugins.modules import sonic_interface_port, vlan, vlan_member


class ModuleExit(Exception):
    def __init__(self, result):
        self.result = result


def exit_json(**kwargs):
    raise ModuleExit(kwargs)


@pytest.mark.parametrize('module,params,table,key,current,wanted', (
    (vlan, dict(vlanid=42, state='present', dhcp_servers=[]),
     'VLAN', 'Vlan42', {}, {'vlanid': '42'}),
    (vlan, dict(vlanid=42, state='absent', dhcp_servers=[]),
     'VLAN', 'Vlan42', {'vlanid': '42'}, None),
    (vlan_member, dict(vlanid=42, interface='Ethernet0', state='present', tagged=True),
     'VLAN_MEMBER', 'Vlan42|Ethernet0', {}, {'tagging_mode': 'tagged'}),
    (vlan_member, dict(vlanid=42, interface='Ethernet0', state='absent', tagged=None),
     'VLAN_MEMBER', 'Vlan42|Ethernet0', {'tagging_mode': 'tagged'}, None),
    (sonic_interface_port, dict(interface='Ethernet0', enabled=False),
     'PORT', 'Ethernet0', {'speed': '10000', 'admin_status': 'up'}, {'speed': '10000'}),
))
@pytest.mark.parametrize('check_mode', (True, False))
@pytest.mark.parametrize('already_applied', (True, False))
def test_module_changes_and_diff(monkeypatch, module, params, table, key, current, wanted,
                                 check_mode, already_applied):
    if already_applied:
        current = wanted or {}
    fake_module = SimpleNamespace(params=params, check_mode=check_mode, exit_json=exit_json)
    db = Mock()
    db.get_entry.return_value = current
    db.get_table.return_value = {key: current}
    monkeypatch.setattr(module, 'AnsibleModule', Mock(return_value=fake_module))
    monkeypatch.setattr(module, 'HAS_SWSSCOMMON_LIBRARY', True)
    monkeypatch.setattr(module, 'swsscommon', SimpleNamespace(ConfigDBConnector=Mock(return_value=db)), raising=False)

    with pytest.raises(ModuleExit) as result:
        module.run_module()

    assert result.value.result['changed'] is (not already_applied)
    assert result.value.result['diff'] == {'before': current, 'after': wanted or {}}
    db.connect.assert_called_once_with()
    if check_mode or already_applied:
        db.set_entry.assert_not_called()
    else:
        db.set_entry.assert_called_once_with(table, key, wanted)
