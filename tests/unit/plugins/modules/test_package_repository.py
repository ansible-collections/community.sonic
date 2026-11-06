# -*- coding: utf-8 -*-
#
# GNU General Public License v3.0+ (see https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

"""Unit tests for the package_repository module, run against the fake sonic-package-manager."""

from __future__ import (absolute_import, division, print_function)
__metaclass__ = type

import pytest

from ansible_collections.community.sonic.plugins.module_utils import package_manager
from ansible_collections.community.sonic.plugins.modules import package_repository
from ansible_collections.community.sonic.tests.unit.fake_spm import BUILT_IN, record


REPO = 'registry.example.net/sonic/my-exporter'
ADD = ['repository', 'add', 'my-exporter', REPO, '--default-reference', '1.4.2', '--description', 'Prometheus exporter']
PARAMS = dict(name='my-exporter', repository=REPO, default_reference='1.4.2', description='Prometheus exporter')
VIEW = dict(repository=REPO, default_reference='1.4.2', description='Prometheus exporter')


def seed_exporter(spm, **kwargs):
    db = dict(BUILT_IN)
    db['my-exporter'] = record(REPO, 'Prometheus exporter', '1.4.2', **kwargs)
    spm.seed(db)


def test_add(spm, run_module):
    result = run_module(package_repository, PARAMS)
    assert result['changed'] is True
    assert result['name'] == 'my-exporter'
    assert result['repository'] == REPO
    assert result['default_reference'] == '1.4.2'
    assert result['description'] == 'Prometheus exporter'
    assert result['status'] == 'Not Installed'
    assert result['diff'] == {'before': {}, 'after': VIEW}
    assert result['commands'] == ['%s %s' % (spm.BIN, ' '.join(ADD))]
    assert spm.calls == [ADD]
    assert spm.database()['my-exporter'] == record(REPO, 'Prometheus exporter', '1.4.2')


def test_add_minimal(spm, run_module):
    result = run_module(package_repository, dict(name='my-exporter', repository=REPO))
    assert result['changed'] is True
    assert result['default_reference'] is None
    assert result['description'] is None
    assert spm.calls == [['repository', 'add', 'my-exporter', REPO]]


def test_add_check_mode(spm, run_module):
    result = run_module(package_repository, PARAMS, check_mode=True)
    assert result['changed'] is True
    assert result['status'] == 'Not Installed'
    assert result['diff'] == {'before': {}, 'after': VIEW}
    assert result['commands'] == []
    assert spm.calls == []
    assert 'my-exporter' not in spm.database()


def test_add_idempotent(spm, run_module):
    seed_exporter(spm)
    for check_mode in (False, True):
        result = run_module(package_repository, PARAMS, check_mode=check_mode)
        assert result['changed'] is False
        assert result['diff'] == {'before': VIEW, 'after': VIEW}
        assert result['status'] == 'Not Installed'
        assert result['commands'] == []
    assert spm.calls == []


def test_omitted_options_keep_stored_values(spm, run_module):
    seed_exporter(spm)
    result = run_module(package_repository, dict(name='my-exporter', repository=REPO))
    assert result['changed'] is False
    assert result['default_reference'] == '1.4.2'
    assert result['description'] == 'Prometheus exporter'
    assert spm.calls == []


def test_modify_removes_and_re_adds(spm, run_module):
    seed_exporter(spm)
    params = dict(PARAMS, default_reference='1.5.0')
    result = run_module(package_repository, params)
    assert result['changed'] is True
    assert result['default_reference'] == '1.5.0'
    assert result['diff']['before'] == VIEW
    assert result['diff']['after'] == dict(VIEW, default_reference='1.5.0')
    assert spm.calls == [
        ['repository', 'remove', 'my-exporter'],
        ['repository', 'add', 'my-exporter', REPO, '--default-reference', '1.5.0', '--description', 'Prometheus exporter'],
    ]
    assert spm.database()['my-exporter']['default-reference'] == '1.5.0'


def test_modify_check_mode(spm, run_module):
    seed_exporter(spm)
    result = run_module(package_repository, dict(PARAMS, description='changed'), check_mode=True)
    assert result['changed'] is True
    assert result['description'] == 'changed'
    assert spm.calls == []
    assert spm.database()['my-exporter']['description'] == 'Prometheus exporter'


def test_modify_installed_fails(spm, run_module):
    seed_exporter(spm, version='1.4.2', installed=True)
    result = run_module(package_repository, dict(PARAMS, default_reference='1.5.0'), expect_failure=True)
    assert result['msg'] == ('package my-exporter is installed (version 1.4.2); its repository entry can only be '
                             'changed while the package is not installed')
    assert spm.calls == []


def test_installed_unchanged_is_fine(spm, run_module):
    seed_exporter(spm, version='1.4.2', installed=True)
    result = run_module(package_repository, PARAMS)
    assert result['changed'] is False
    assert result['status'] == 'Installed'


def test_modify_built_in_fails(spm, run_module):
    result = run_module(package_repository, dict(name='database', repository='other'), expect_failure=True)
    assert result['msg'] == 'package database is built-in and cannot be modified'
    assert spm.calls == []


def test_remove(spm, run_module):
    seed_exporter(spm)
    result = run_module(package_repository, dict(name='my-exporter', state='absent'))
    assert result['changed'] is True
    assert result['status'] == 'Absent'
    assert result['repository'] is None
    assert result['diff'] == {'before': VIEW, 'after': {}}
    assert spm.calls == [['repository', 'remove', 'my-exporter']]
    assert 'my-exporter' not in spm.database()


def test_remove_check_mode(spm, run_module):
    seed_exporter(spm)
    result = run_module(package_repository, dict(name='my-exporter', state='absent'), check_mode=True)
    assert result['changed'] is True
    assert result['status'] == 'Absent'
    assert spm.calls == []
    assert 'my-exporter' in spm.database()


def test_remove_idempotent(spm, run_module):
    for check_mode in (False, True):
        result = run_module(package_repository, dict(name='my-exporter', state='absent'), check_mode=check_mode)
        assert result['changed'] is False
        assert result['status'] == 'Absent'
        assert result['diff'] == {'before': {}, 'after': {}}
    assert spm.calls == []


def test_remove_installed_fails(spm, run_module):
    seed_exporter(spm, version='1.4.2', installed=True)
    result = run_module(package_repository, dict(name='my-exporter', state='absent'), expect_failure=True)
    assert result['msg'] == ('package my-exporter is installed (version 1.4.2); uninstall it with '
                             'community.sonic.package state=absent before removing its repository')
    assert spm.calls == []


def test_remove_built_in_fails(spm, run_module):
    result = run_module(package_repository, dict(name='database', state='absent'), expect_failure=True)
    assert result['msg'] == 'package database is built-in and cannot be removed'


def test_present_requires_repository(spm, run_module):
    result = run_module(package_repository, dict(name='my-exporter'), expect_failure=True)
    assert 'repository' in result['msg']


@pytest.mark.parametrize('params', (PARAMS, dict(name='my-exporter', state='absent')))
def test_not_root_fails_with_become_hint(spm, run_module, params):
    seed_exporter(spm)
    if params.get('state') != 'absent':
        params = dict(params, description='changed')
    spm.euid = 1000
    result = run_module(package_repository, params, expect_failure=True)
    assert result['msg'].startswith('sonic-package-manager repository remove my-exporter requires root privileges')
    assert 'become: true' in result['msg']
    assert spm.calls == []


def test_not_root_can_read_state(spm, run_module):
    seed_exporter(spm)
    spm.euid = 1000
    result = run_module(package_repository, PARAMS)
    assert result['changed'] is False
    result = run_module(package_repository, dict(PARAMS, description='changed'), check_mode=True)
    assert result['changed'] is True
    assert spm.calls == []


def test_state_from_list_when_database_unreadable(spm, run_module, monkeypatch):
    seed_exporter(spm)
    monkeypatch.setattr(package_manager, 'DATABASE_PATH', '/nonexistent/packages.json')
    result = run_module(package_repository, dict(name='my-exporter', repository=REPO, description='Prometheus exporter'))
    assert result['changed'] is False
    assert spm.calls == [['list']]


def test_spm_failure_is_reported(spm, run_module):
    spm.fail_next = (1, 'Failed to add repository my-exporter: Package my-exporter already exists in database\n')
    result = run_module(package_repository, PARAMS, expect_failure=True)
    assert result['msg'] == ('sonic-package-manager repository add my-exporter failed with rc 1: Failed to add '
                             'repository my-exporter: Package my-exporter already exists in database')
    assert result['commands'] == ['%s %s' % (spm.BIN, ' '.join(ADD))]
