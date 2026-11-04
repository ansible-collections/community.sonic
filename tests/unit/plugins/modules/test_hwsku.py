# -*- coding: utf-8 -*-
#
# GNU General Public License v3.0+ (see https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

"""Unit tests for the hwsku module.

The host is simulated in a temporary directory: the module's path constants
are redirected there, ``os.geteuid`` reports root and ``sonic-cfggen`` is
replaced by a small fake that builds a ``PORT`` table from the
``port_config.ini`` it is pointed at and answers ``-d -v`` with a configurable
running HWSKU.
"""

from __future__ import (absolute_import, division, print_function)
__metaclass__ = type

import json
import os
import stat

import pytest

from ansible.module_utils import basic

from ansible_collections.community.sonic.plugins.modules import hwsku


PLATFORM = 'x86_64-kvm_x86_64-r0'

S6000_PORT_CONFIG = """# name          lanes                alias       index   speed
Ethernet0       25,26,27,28          fortyGigE0/0    0   40000
Ethernet4       29,30,31,32          fortyGigE0/4    1   40000
Ethernet8       33,34,35,36          fortyGigE0/8    2   40000
"""

S6100_PORT_CONFIG = """# name          lanes                alias            index   speed
Ethernet0       49,50,51,52          fortyGigE1/1/1       0   40000
Ethernet4       53,54,55,56          fortyGigE1/1/2       1   40000
Ethernet64      1,2,3,4              fortyGigE1/3/1       16  40000
"""

PLATFORM_JSON_PORTS = {
    'Ethernet0': {'lanes': '1,2,3,4', 'alias': 'Eth1', 'index': '1', 'speed': '100000'},
}

ENVIRONMENT = """SONIC_VERSION=SONiC-OS-master.0-dirty-20261103
PLATFORM=x86_64-kvm_x86_64-r0
HWSKU=Force10-S6000
DEVICE_TYPE=LeafRouter
ASIC_TYPE=vs
"""

SAVED_PORTS = {
    'Ethernet0': {'lanes': '25,26,27,28', 'alias': 'fortyGigE0/0', 'index': '0', 'speed': '40000',
                  'admin_status': 'up', 'mtu': '9100', 'description': 'uplink'},
    'Ethernet4': {'lanes': '29,30,31,32', 'alias': 'fortyGigE0/4', 'index': '1', 'speed': '40000',
                  'admin_status': 'down', 'mtu': '9100', 'fec': 'rs'},
    'Ethernet8': {'lanes': '33,34,35,36', 'alias': 'fortyGigE0/8', 'index': '2', 'speed': '40000',
                  'admin_status': 'up', 'mtu': '9100'},
}

SAVED_CONFIG = {
    'DEVICE_METADATA': {'localhost': {'hostname': 'sonic', 'hwsku': 'Force10-S6000', 'platform': PLATFORM,
                                      'type': 'LeafRouter'}},
    'PORT': SAVED_PORTS,
    'VLAN': {'Vlan100': {'vlanid': '100'}},
    'VLAN_MEMBER': {'Vlan100|Ethernet8': {'tagging_mode': 'untagged'}},
}


def parse_port_config(text):
    ports = {}
    for line in text.splitlines():
        if not line.strip() or line.startswith('#'):
            continue
        name, lanes, alias, index, speed = line.split()
        ports[name] = {'lanes': lanes, 'alias': alias, 'index': index, 'speed': speed}
    return ports


class FakeHost(object):
    """A SONiC host in a temporary directory plus a fake sonic-cfggen."""

    def __init__(self, root):
        self.root = str(root)
        self.device_dir = os.path.join(self.root, 'usr/share/sonic/device')
        self.platform_dir = os.path.join(self.device_dir, PLATFORM)
        self.environment = os.path.join(self.root, 'etc/sonic/sonic-environment')
        self.config_db_json = os.path.join(self.root, 'etc/sonic/config_db.json')
        self.machine_conf = os.path.join(self.root, 'host/machine.conf')
        self.running_hwsku = 'Force10-S6000'
        self.cfggen_rc = 0
        self.commands = []
        os.makedirs(self.platform_dir)
        os.makedirs(os.path.dirname(self.environment))
        self.add_hwsku('Force10-S6000', S6000_PORT_CONFIG)
        self.write(self.environment, ENVIRONMENT)
        self.write_config(SAVED_CONFIG)

    # -- fixture plumbing ---------------------------------------------------------

    def write(self, path, text):
        parent = os.path.dirname(path)
        if not os.path.isdir(parent):
            os.makedirs(parent)
        with open(path, 'w') as f:
            f.write(text)

    def read(self, path):
        with open(path) as f:
            return f.read()

    def write_config(self, config):
        self.write(self.config_db_json, json.dumps(config, indent=4) + '\n')

    def config(self):
        return json.loads(self.read(self.config_db_json))

    def environment_values(self):
        return hwsku.parse_environment(self.read(self.environment))

    def hwsku_dir(self, name):
        return os.path.join(self.platform_dir, name)

    def add_hwsku(self, name, port_config=None, where=None):
        path = os.path.join(where or self.platform_dir, name)
        os.makedirs(path)
        if port_config is not None:
            self.write(os.path.join(path, 'port_config.ini'), port_config)
        self.write(os.path.join(path, 'sai.profile'), 'SAI_INIT_CONFIG_FILE=/usr/share/sonic/hwsku/td2.config.bcm\n')
        return path

    def run_command(self, args, **kwargs):
        self.commands.append(list(args))
        assert args[0] == '/usr/local/bin/sonic-cfggen'
        if args[1:3] == ['-d', '-v']:
            if self.running_hwsku is None:
                return 1, '', 'Unable to connect to redis'
            return 0, self.running_hwsku + '\n', ''
        assert args[1:3] == ['-H', '-k']
        if self.cfggen_rc:
            return self.cfggen_rc, '', 'Failed to get port config\n'
        port_config = args[args.index('-p') + 1]
        if port_config.endswith('platform.json'):
            ports = PLATFORM_JSON_PORTS
        else:
            ports = parse_port_config(self.read(port_config))
        data = {'DEVICE_METADATA': {'localhost': {'hwsku': args[3], 'platform': PLATFORM}}, 'PORT': ports}
        return 0, json.dumps(data, indent=4), ''


@pytest.fixture
def host(tmp_path, monkeypatch):
    fake = FakeHost(tmp_path)
    monkeypatch.setattr(hwsku, 'DEVICE_DIR', fake.device_dir)
    monkeypatch.setattr(hwsku, 'SONIC_ENVIRONMENT', fake.environment)
    monkeypatch.setattr(hwsku, 'CONFIG_DB_JSON', fake.config_db_json)
    monkeypatch.setattr(hwsku, 'MACHINE_CONF', fake.machine_conf)
    monkeypatch.setattr(hwsku.os, 'geteuid', lambda: 0)
    monkeypatch.setattr(basic.AnsibleModule, 'run_command', lambda self, args, **kw: fake.run_command(args, **kw))
    real_get_bin_path = basic.AnsibleModule.get_bin_path

    def get_bin_path(self, name, *args, **kwargs):
        if name == 'sonic-cfggen':
            return '/usr/local/bin/sonic-cfggen'
        return real_get_bin_path(self, name, *args, **kwargs)

    monkeypatch.setattr(basic.AnsibleModule, 'get_bin_path', get_bin_path)
    return fake


def expected_ports(port_config, old=None):
    return hwsku.merge_port_table(SAVED_PORTS if old is None else old, parse_port_config(port_config))


# -- pure helpers -----------------------------------------------------------------

def test_parse_environment():
    assert hwsku.parse_environment('# comment\n\nA=1\nexport B="two words"\nC=\'3\'\nbogus line\n') == {
        'A': '1', 'B': 'two words', 'C': '3'}


def test_set_environment_value_replaces_keeps_order_and_appends():
    text = 'PLATFORM=p\nHWSKU=old\nASIC_TYPE=vs\n'
    assert hwsku.set_environment_value(text, 'HWSKU', 'new') == 'PLATFORM=p\nHWSKU=new\nASIC_TYPE=vs\n'
    assert hwsku.set_environment_value('PLATFORM=p', 'HWSKU', 'new') == 'PLATFORM=p\nHWSKU=new\n'
    assert hwsku.set_environment_value('PLATFORM=p\r\nHWSKU=old\r\n', 'HWSKU', 'new') == 'PLATFORM=p\r\nHWSKU=new\r\n'
    assert hwsku.set_environment_value('', 'HWSKU', 'new') == 'HWSKU=new\n'


def test_merge_port_table_keeps_description_and_admin_status_only():
    new = parse_port_config(S6100_PORT_CONFIG)
    merged = hwsku.merge_port_table(SAVED_PORTS, new)
    assert set(merged) == {'Ethernet0', 'Ethernet4', 'Ethernet64'}
    assert merged['Ethernet0'] == dict(new['Ethernet0'], admin_status='up', description='uplink')
    assert merged['Ethernet4'] == dict(new['Ethernet4'], admin_status='down')  # fec and mtu are dropped
    assert merged['Ethernet64'] == new['Ethernet64']
    assert new['Ethernet0'] == parse_port_config(S6100_PORT_CONFIG)['Ethernet0']  # input not modified


@pytest.mark.parametrize('name', ('', '.', '..', '../etc', 'a/b', '-leading', 'with space'))
def test_validate_hwsku_name_rejects(name):
    with pytest.raises(hwsku.HwskuError):
        hwsku.validate_hwsku_name(name)


def test_directory_manifest_ignores_mode(tmp_path):
    a = tmp_path / 'a'
    b = tmp_path / 'b'
    for d in (a, b):
        (d / 'sub').mkdir(parents=True)
        (d / 'port_config.ini').write_text('x\n')
        (d / 'sub' / 'file').write_text('y\n')
        os.symlink('port_config.ini', str(d / 'link'))
    os.chmod(str(a / 'port_config.ini'), 0o600)
    os.chmod(str(b / 'port_config.ini'), 0o755)
    assert hwsku.directory_manifest(str(a)) == hwsku.directory_manifest(str(b))
    assert set(hwsku.directory_manifest(str(a))) == {'port_config.ini', 'sub/file', 'link'}
    assert hwsku.directory_manifest(str(a))['link'] == 'symlink:port_config.ini'
    assert hwsku.directory_manifest(str(tmp_path / 'missing')) == {}
    (b / 'sub' / 'file').write_text('changed\n')
    assert hwsku.directory_manifest(str(a)) != hwsku.directory_manifest(str(b))


def test_port_config_arguments(tmp_path):
    platform_dir = tmp_path / 'platform'
    sku = platform_dir / 'SKU'
    sku.mkdir(parents=True)
    with pytest.raises(hwsku.HwskuError) as excinfo:
        hwsku.port_config_arguments(str(sku), str(platform_dir))
    assert 'set regenerate_ports=false' in str(excinfo.value)
    (platform_dir / 'platform.json').write_text('{}')
    assert hwsku.port_config_arguments(str(sku), str(platform_dir)) == ['-p', str(platform_dir / 'platform.json')]
    (sku / 'hwsku.json').write_text('{}')
    assert hwsku.port_config_arguments(str(sku), str(platform_dir)) == [
        '-p', str(platform_dir / 'platform.json'), '-S', str(sku / 'hwsku.json')]
    (sku / 'port_config.ini').write_text('')
    assert hwsku.port_config_arguments(str(sku), str(platform_dir)) == ['-p', str(sku / 'port_config.ini')]


# -- module runs ------------------------------------------------------------------

def test_requires_root(host, run_module, monkeypatch):
    monkeypatch.setattr(hwsku.os, 'geteuid', lambda: 1000)
    result = run_module(hwsku, dict(name='Force10-S6000'), expect_failure=True)
    assert result['msg'] == 'community.sonic.hwsku needs root to write /etc/sonic and %s; run it with become: true' % host.device_dir
    assert host.commands == []


@pytest.mark.parametrize('check_mode', (True, False))
def test_read_only_current_hwsku(host, run_module, check_mode):
    environment_before = host.read(host.environment)
    config_before = host.read(host.config_db_json)
    result = run_module(hwsku, dict(name='Force10-S6000'), check_mode=check_mode)
    assert result['changed'] is False
    assert result['platform'] == PLATFORM
    assert result['hwsku'] == 'Force10-S6000'
    assert result['previous_hwsku'] == 'Force10-S6000'
    assert result['running_hwsku'] == 'Force10-S6000'
    assert result['hwsku_dir'] == host.hwsku_dir('Force10-S6000')
    assert result['reboot_required'] is False
    assert result['ports_regenerated'] is False
    assert result['diff']['before'] == result['diff']['after'] == {
        'hwsku': 'Force10-S6000', 'environment_hwsku': 'Force10-S6000'}
    assert 'PORT' not in result['diff']['after']
    # Nothing is written and sonic-cfggen is only asked for the running HWSKU.
    assert host.read(host.environment) == environment_before
    assert host.read(host.config_db_json) == config_before
    assert host.commands == [['/usr/local/bin/sonic-cfggen', '-d', '-v', 'DEVICE_METADATA.localhost.hwsku']]


def test_read_only_reports_pending_reboot(host, run_module):
    host.running_hwsku = 'Arista-7050-QX32'
    result = run_module(hwsku, dict(name='Force10-S6000'))
    assert result['changed'] is False
    assert result['reboot_required'] is True
    assert result['running_hwsku'] == 'Arista-7050-QX32'


def test_running_hwsku_unknown(host, run_module):
    host.running_hwsku = None
    result = run_module(hwsku, dict(name='Force10-S6000'))
    assert result['changed'] is False
    assert result['reboot_required'] is False
    assert 'running_hwsku' not in result


@pytest.mark.parametrize('check_mode', (True, False))
def test_switch_to_builtin_hwsku(host, run_module, check_mode):
    host.add_hwsku('Force10-S6100', S6100_PORT_CONFIG)
    environment_before = host.read(host.environment)
    config_before = host.config()

    result = run_module(hwsku, dict(name='Force10-S6100'), check_mode=check_mode)

    wanted_ports = expected_ports(S6100_PORT_CONFIG)
    assert result['changed'] is True
    assert result['reboot_required'] is True
    assert result['ports_regenerated'] is True
    assert result['hwsku'] == 'Force10-S6100'
    assert result['previous_hwsku'] == 'Force10-S6000'
    assert result['platform'] == PLATFORM
    assert result['diff'] == {
        'before': {'hwsku': 'Force10-S6000', 'environment_hwsku': 'Force10-S6000', 'PORT': SAVED_PORTS},
        'after': {'hwsku': 'Force10-S6100', 'environment_hwsku': 'Force10-S6100', 'PORT': wanted_ports},
    }
    assert host.commands[-1] == ['/usr/local/bin/sonic-cfggen', '-H', '-k', 'Force10-S6100',
                                 '-p', os.path.join(host.hwsku_dir('Force10-S6100'), 'port_config.ini'), '--print-data']
    if check_mode:
        assert host.read(host.environment) == environment_before
        assert host.config() == config_before
        return

    assert host.environment_values()['HWSKU'] == 'Force10-S6100'
    assert host.read(host.environment) == environment_before.replace('HWSKU=Force10-S6000', 'HWSKU=Force10-S6100')
    config = host.config()
    assert config['DEVICE_METADATA']['localhost'] == dict(config_before['DEVICE_METADATA']['localhost'], hwsku='Force10-S6100')
    assert config['PORT'] == wanted_ports
    assert config['PORT']['Ethernet0']['description'] == 'uplink'
    assert config['PORT']['Ethernet4']['admin_status'] == 'down'
    assert 'mtu' not in config['PORT']['Ethernet0']
    assert 'Ethernet8' not in config['PORT']
    # Unrelated tables are untouched.
    assert config['VLAN'] == SAVED_CONFIG['VLAN']
    assert config['VLAN_MEMBER'] == SAVED_CONFIG['VLAN_MEMBER']
    assert 'backup_file' not in result

    # The second run is a no-op but the reboot is still pending.
    result = run_module(hwsku, dict(name='Force10-S6100'))
    assert result['changed'] is False
    assert result['reboot_required'] is True
    assert result['running_hwsku'] == 'Force10-S6000'
    assert result['previous_hwsku'] == 'Force10-S6100'
    host.running_hwsku = 'Force10-S6100'
    result = run_module(hwsku, dict(name='Force10-S6100'))
    assert result['changed'] is False
    assert result['reboot_required'] is False


def test_switch_without_regenerating_ports(host, run_module):
    host.add_hwsku('Force10-S6100', S6100_PORT_CONFIG)
    result = run_module(hwsku, dict(name='Force10-S6100', regenerate_ports=False))
    assert result['changed'] is True
    assert result['ports_regenerated'] is False
    assert 'PORT' not in result['diff']['after']
    config = host.config()
    assert config['PORT'] == SAVED_PORTS
    assert config['DEVICE_METADATA']['localhost']['hwsku'] == 'Force10-S6100'
    assert host.environment_values()['HWSKU'] == 'Force10-S6100'
    assert len(host.commands) == 1  # only the running HWSKU query


def test_completes_a_partial_switch(host, run_module):
    # sonic-environment already points at the new HWSKU but the saved configuration does not.
    host.add_hwsku('Force10-S6100', S6100_PORT_CONFIG)
    host.write(host.environment, ENVIRONMENT.replace('HWSKU=Force10-S6000', 'HWSKU=Force10-S6100'))
    result = run_module(hwsku, dict(name='Force10-S6100'))
    assert result['changed'] is True
    assert result['previous_hwsku'] == 'Force10-S6100'
    config = host.config()
    assert config['DEVICE_METADATA']['localhost']['hwsku'] == 'Force10-S6100'
    assert config['PORT'] == expected_ports(S6100_PORT_CONFIG)


def test_backup(host, run_module):
    host.add_hwsku('Force10-S6100', S6100_PORT_CONFIG)
    original = host.read(host.config_db_json)
    result = run_module(hwsku, dict(name='Force10-S6100', backup=True))
    assert result['changed'] is True
    assert result['backup_file'].startswith(host.config_db_json + '.')
    assert host.read(result['backup_file']) == original
    assert host.config()['DEVICE_METADATA']['localhost']['hwsku'] == 'Force10-S6100'

    result = run_module(hwsku, dict(name='Force10-S6100', backup=True))
    assert result['changed'] is False
    assert 'backup_file' not in result


def test_unknown_hwsku_without_src(host, run_module):
    result = run_module(hwsku, dict(name='Nope-SKU'), expect_failure=True)
    assert result['msg'] == 'HWSKU "Nope-SKU" does not exist under %s; pass src to install it' % host.platform_dir
    assert host.environment_values()['HWSKU'] == 'Force10-S6000'


def test_invalid_name(host, run_module):
    result = run_module(hwsku, dict(name='../Force10-S6000'), expect_failure=True)
    assert result['msg'].startswith('invalid HWSKU name "../Force10-S6000"')


def test_missing_src(host, run_module):
    result = run_module(hwsku, dict(name='Test-SKU', src=os.path.join(host.root, 'nowhere')), expect_failure=True)
    assert result['msg'] == 'src "%s" is not a directory on the SONiC host' % os.path.join(host.root, 'nowhere')


def test_no_port_configuration(host, run_module):
    host.add_hwsku('Bare-SKU')
    result = run_module(hwsku, dict(name='Bare-SKU'), expect_failure=True)
    assert result['msg'].startswith('found neither %s' % os.path.join(host.hwsku_dir('Bare-SKU'), 'port_config.ini'))
    assert 'set regenerate_ports=false' in result['msg']
    assert host.environment_values()['HWSKU'] == 'Force10-S6000'

    result = run_module(hwsku, dict(name='Bare-SKU', regenerate_ports=False))
    assert result['changed'] is True
    assert host.environment_values()['HWSKU'] == 'Bare-SKU'


def test_platform_json_route(host, run_module):
    host.write(os.path.join(host.platform_dir, 'platform.json'), '{"interfaces": {}}\n')
    sku = host.add_hwsku('Json-SKU')
    host.write(os.path.join(sku, 'hwsku.json'), '{"interfaces": {}}\n')
    result = run_module(hwsku, dict(name='Json-SKU'))
    assert result['changed'] is True
    assert host.commands[-1] == ['/usr/local/bin/sonic-cfggen', '-H', '-k', 'Json-SKU',
                                 '-p', os.path.join(host.platform_dir, 'platform.json'),
                                 '-S', os.path.join(sku, 'hwsku.json'), '--print-data']
    assert host.config()['PORT'] == hwsku.merge_port_table(SAVED_PORTS, PLATFORM_JSON_PORTS)


def test_cfggen_failure(host, run_module):
    host.add_hwsku('Force10-S6100', S6100_PORT_CONFIG)
    host.cfggen_rc = 1
    result = run_module(hwsku, dict(name='Force10-S6100'), expect_failure=True)
    assert result['msg'] == 'sonic-cfggen failed to build the PORT table for HWSKU "Force10-S6100": Failed to get port config'
    assert host.environment_values()['HWSKU'] == 'Force10-S6000'
    assert host.config()['DEVICE_METADATA']['localhost']['hwsku'] == 'Force10-S6000'


def test_missing_sonic_environment(host, run_module):
    os.unlink(host.environment)
    result = run_module(hwsku, dict(name='Force10-S6000'), expect_failure=True)
    assert result['msg'] == '%s does not exist; is this a SONiC host?' % host.environment


def test_missing_saved_config(host, run_module):
    os.unlink(host.config_db_json)
    result = run_module(hwsku, dict(name='Force10-S6000'), expect_failure=True)
    assert result['msg'] == '%s does not exist; save the running configuration first (config save -y)' % host.config_db_json


def test_platform_from_machine_conf(host, run_module):
    host.write(host.environment, ENVIRONMENT.replace('PLATFORM=x86_64-kvm_x86_64-r0\n', ''))
    host.write(host.machine_conf, 'onie_version=2020.11\nonie_platform=%s\n' % PLATFORM)
    result = run_module(hwsku, dict(name='Force10-S6000'))
    assert result['changed'] is False
    assert result['platform'] == PLATFORM


# -- src installation ---------------------------------------------------------------

@pytest.mark.parametrize('check_mode', (True, False))
def test_install_from_src(host, run_module, check_mode):
    src = host.add_hwsku('Test-SKU', S6100_PORT_CONFIG, where=os.path.join(host.root, 'home/admin'))
    os.makedirs(os.path.join(src, 'sub'))
    host.write(os.path.join(src, 'sub', 'buffers.json.j2'), '{}\n')
    host.write(os.path.join(src, 'hook.sh'), '#!/bin/sh\n')
    os.chmod(os.path.join(src, 'hook.sh'), 0o700)
    os.symlink('port_config.ini', os.path.join(src, 'port_config.link'))
    dest = host.hwsku_dir('Test-SKU')

    result = run_module(hwsku, dict(name='Test-SKU', src=src), check_mode=check_mode)

    manifest = hwsku.directory_manifest(src)
    assert result['changed'] is True
    assert result['reboot_required'] is True
    assert result['hwsku_dir'] == dest
    assert result['diff']['before']['files'] == {}
    assert result['diff']['after']['files'] == manifest
    assert result['diff']['after']['PORT'] == expected_ports(S6100_PORT_CONFIG)
    # The PORT table is generated from src because the HWSKU is not installed yet.
    assert host.commands[-1][4:6] == ['-p', os.path.join(src, 'port_config.ini')]
    if check_mode:
        assert not os.path.exists(dest)
        assert host.environment_values()['HWSKU'] == 'Force10-S6000'
        return

    assert hwsku.directory_manifest(dest) == manifest
    assert stat.S_IMODE(os.stat(os.path.join(dest, 'port_config.ini')).st_mode) == 0o644
    assert stat.S_IMODE(os.stat(os.path.join(dest, 'hook.sh')).st_mode) == 0o755
    assert os.readlink(os.path.join(dest, 'port_config.link')) == 'port_config.ini'
    assert host.environment_values()['HWSKU'] == 'Test-SKU'
    assert host.config()['DEVICE_METADATA']['localhost']['hwsku'] == 'Test-SKU'
    assert host.config()['PORT'] == expected_ports(S6100_PORT_CONFIG)

    # Idempotent, and mode/ownership differences are not changes.
    os.chmod(os.path.join(dest, 'port_config.ini'), 0o600)
    os.chmod(os.path.join(dest, 'sai.profile'), 0o777)
    result = run_module(hwsku, dict(name='Test-SKU', src=src))
    assert result['changed'] is False
    assert result['diff']['before'] == result['diff']['after']
    assert 'PORT' not in result['diff']['after']
    assert stat.S_IMODE(os.stat(os.path.join(dest, 'port_config.ini')).st_mode) == 0o600
    assert host.commands[-1][1:3] == ['-d', '-v']


def test_update_installed_src(host, run_module):
    src = host.add_hwsku('Test-SKU', S6100_PORT_CONFIG, where=os.path.join(host.root, 'home/admin'))
    dest = host.hwsku_dir('Test-SKU')
    run_module(hwsku, dict(name='Test-SKU', src=src))
    config_after_install = host.config()
    environment_after_install = host.read(host.environment)

    # Change the port layout and a file, drop another, add one.
    new_port_config = S6100_PORT_CONFIG + 'Ethernet68      5,6,7,8              fortyGigE1/3/2       17  40000\n'
    host.write(os.path.join(src, 'port_config.ini'), new_port_config)
    os.unlink(os.path.join(src, 'sai.profile'))
    host.write(os.path.join(src, 'extra.conf'), 'x\n')
    host.write(os.path.join(dest, 'stale.conf'), 'stale\n')

    result = run_module(hwsku, dict(name='Test-SKU', src=src), check_mode=True)
    assert result['changed'] is True
    assert result['ports_regenerated'] is True
    assert sorted(result['diff']['before']['files']) == ['port_config.ini', 'sai.profile', 'stale.conf']
    assert sorted(result['diff']['after']['files']) == ['extra.conf', 'port_config.ini']
    assert os.path.exists(os.path.join(dest, 'stale.conf'))
    assert host.config() == config_after_install

    result = run_module(hwsku, dict(name='Test-SKU', src=src))
    assert result['changed'] is True
    assert result['ports_regenerated'] is True
    assert result['previous_hwsku'] == 'Test-SKU'
    assert sorted(os.listdir(dest)) == ['extra.conf', 'port_config.ini']
    assert host.read(os.path.join(dest, 'port_config.ini')) == new_port_config
    config = host.config()
    assert config['PORT'] == expected_ports(new_port_config, config_after_install['PORT'])
    assert 'Ethernet68' in config['PORT']
    assert config['PORT']['Ethernet0']['description'] == 'uplink'
    assert host.read(host.environment) == environment_after_install  # already Test-SKU

    result = run_module(hwsku, dict(name='Test-SKU', src=src))
    assert result['changed'] is False


def test_src_for_current_hwsku_with_same_content_is_not_a_change(host, run_module):
    import shutil
    src = os.path.join(host.root, 'home/admin/Force10-S6000')
    shutil.copytree(host.hwsku_dir('Force10-S6000'), src)
    os.chmod(os.path.join(src, 'port_config.ini'), 0o600)
    result = run_module(hwsku, dict(name='Force10-S6000', src=src))
    assert result['changed'] is False
    assert result['reboot_required'] is False
    assert result['diff']['before']['files'] == result['diff']['after']['files']


def test_empty_src(host, run_module):
    src = os.path.join(host.root, 'home/admin/Empty')
    os.makedirs(src)
    result = run_module(hwsku, dict(name='Empty', src=src), expect_failure=True)
    assert result['msg'] == 'src "%s" is empty' % src
