# -*- coding: utf-8 -*-
#
# GNU General Public License v3.0+ (see https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

"""Shared pytest fixtures for community.sonic unit tests.

``fake_swsscommon``
    A :class:`FakeSwssCommon` instance patched into ``module_utils.config_db``
    so modules see a dict-backed CONFIG_DB. Seed it with
    ``fake_swsscommon.seed({'VLAN': {'Vlan42': {'vlanid': '42'}}})`` and assert
    on ``fake_swsscommon.writes`` or ``fake_swsscommon.get_entry(...)``.

``spm``
    A :class:`FakeSpm` wired into ``AnsibleModule.run_command``/``get_bin_path``
    and ``module_utils.package_manager`` with a ``packages.json`` under
    ``tmp_path``; emulates ``sonic-package-manager`` for the package modules.

``run_module``
    ``run_module(module, params, check_mode=False, expect_failure=False)``
    runs a module's ``run_module()`` with the given parameters and returns the
    ``exit_json`` result dictionary. A ``fail_json`` raises
    :class:`ModuleFailed` unless ``expect_failure`` is set, in which case the
    ``fail_json`` dictionary is returned instead.
"""

from __future__ import (absolute_import, division, print_function)
__metaclass__ = type

import pytest

from ansible.module_utils import basic
from ansible.module_utils.testing import patch_module_args

from ansible_collections.community.sonic.plugins.module_utils import config_db, package_manager
from ansible_collections.community.sonic.tests.unit.fake_spm import FakeSpm
from ansible_collections.community.sonic.tests.unit.fake_swsscommon import FakeSwssCommon


class ModuleExit(Exception):
    """Raised by the patched ``exit_json``; ``result`` holds the module result."""

    def __init__(self, result):
        super(ModuleExit, self).__init__(result.get('msg', 'module exited'))
        self.result = result


class ModuleFailed(Exception):
    """Raised by the patched ``fail_json``; ``result`` holds the failure dictionary."""

    def __init__(self, result):
        super(ModuleFailed, self).__init__(result.get('msg', 'module failed'))
        self.result = result


def _exit_json(self, **kwargs):
    kwargs.setdefault('changed', False)
    raise ModuleExit(kwargs)


def _fail_json(self, msg, **kwargs):
    kwargs['failed'] = True
    kwargs['msg'] = msg
    raise ModuleFailed(kwargs)


@pytest.fixture
def fake_swsscommon(monkeypatch):
    """Dict-backed swsscommon replacement wired into ``module_utils.config_db``."""
    fake = FakeSwssCommon()
    monkeypatch.setattr(config_db, 'swsscommon', fake)
    monkeypatch.setattr(config_db, 'HAS_SWSSCOMMON', True)
    monkeypatch.setattr(config_db, 'SWSSCOMMON_IMPORT_ERROR', None)
    return fake


@pytest.fixture
def spm(monkeypatch, tmp_path):
    """Fake ``sonic-package-manager`` with a ``packages.json`` database under ``tmp_path``."""
    fake = FakeSpm(tmp_path / 'packages.json')
    monkeypatch.setattr(basic.AnsibleModule, 'get_bin_path', fake.get_bin_path)
    monkeypatch.setattr(basic.AnsibleModule, 'run_command', fake.run_command)
    monkeypatch.setattr(package_manager, 'DATABASE_PATH', fake.database_path)
    monkeypatch.setattr(package_manager.os, 'geteuid', lambda: fake.euid)
    return fake


@pytest.fixture
def run_module(monkeypatch, fake_swsscommon):  # pylint: disable=unused-argument,redefined-outer-name
    """Run a module with the given parameters and return its result dictionary."""
    monkeypatch.setattr(basic.AnsibleModule, 'exit_json', _exit_json)
    monkeypatch.setattr(basic.AnsibleModule, 'fail_json', _fail_json)

    def _run(module, params, check_mode=False, expect_failure=False):
        args = dict(params)
        if check_mode:
            args['_ansible_check_mode'] = True
        with patch_module_args(args):
            try:
                module.run_module()
            except ModuleExit as e:
                if expect_failure:
                    raise AssertionError('module exited successfully but a failure was expected: %r' % (e.result,))
                return e.result
            except ModuleFailed as e:
                if not expect_failure:
                    raise
                return e.result
        raise AssertionError('module returned without calling exit_json or fail_json')

    return _run
