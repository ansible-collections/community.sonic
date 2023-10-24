import sys
import importlib
from ansible.module_utils import basic
from ansible_collections.community.sonic.plugins.module_utils.imports import _set_fake_import, _unset_fake_import


class ModuleFailJSON(Exception):
    pass


class ModuleExitJSON(Exception):
    pass


def fail_json(*args, **kwargs):
    kwargs['failed'] = True
    raise ModuleFailJSON(kwargs)


def exit_json(*args, **kwargs):
    if 'changed' not in kwargs:
        kwargs['changed'] = False
    raise ModuleExitJSON(kwargs)


class fake_environment:
    """Setup a fake/mock environment for basic SONiC modules to run in

    Args:
        module: The (imported) ansible module
        db_tables: The config db tables as a dict
        module_args: the arguments to pass to the module, including module parameters and ansible specfic ones
    """
    def __init__(self, module, db_tables, **module_args):
        self._connected = False
        self._module = module
        self._db_tables = db_tables if db_tables else dict()
        self._module_args = {'ANSIBLE_MODULE_ARGS': module_args}
        # Save standard exit methods for AnsibleModule so they can be restored on __exit__
        self._real_fail_json = getattr(basic.AnsibleModule, 'fail_json')
        self._real_exit_json = getattr(basic.AnsibleModule, 'exit_json')
        self._failed = False
        self._result = None

    @property
    def module(self):
        return self._module

    @property
    def failed(self):
        """Whether the ansible module exited with a failure, default is False"""
        return self._failed

    @property
    def result(self):
        """The result returned from the module run, default is None"""
        return self._result

    @property
    def db_tables(self):
        """Returns a copy of current config DB tables"""
        return dict(self._db_tables)

    def ConfigDBConnector(self):
        # We pretend to be both the swsscommon class as well as the actual config DB connector
        return self

    def connect(self):
        # Mock config db connector method
        self._connected = True

    def get_entry(self, table, key):
        # Mock config db connector method
        if not self._connected:
            raise Exception(f'get_entry called with table "{table}" and key "{key}" before connect')
        table_val = self._db_tables.get(table, {})
        return table_val.get(key, {})

    def set_entry(self, table, key, value):
        # Mock config db connector method
        if not self._connected:
            raise Exception(f'set_entry called with table "{table}", key "{key}" and value "{value}" before connect')
        table_val = self._db_tables.get(table, {})
        table_val[key] = value
        self._db_tables[table] = table_val

    def get_table(self, table):
        # Mock config db connector method
        if not self._connected:
            raise Exception(f'get_table called with table "{table}" before connect')
        return self._db_tables.get(table, {})

    def __enter__(self):
        # ansible modules get their arguments from either a file, sys.argv[1] or STDIN and stores the bytes in _ANSIBLE_ARGS
        # So overwrite the global variable with our own data
        json_args = basic.jsonify(self._module_args).encode('utf-8')
        setattr(basic, '_ANSIBLE_ARGS', json_args)
        # Use mock functions to raise and exception
        setattr(basic.AnsibleModule, 'fail_json', fail_json)
        setattr(basic.AnsibleModule, 'exit_json', exit_json)
        # Mock the swsscommon module using the current module
        _set_fake_import('swsscommon', self)
        # Reload the module so the mocked swsscommon works
        importlib.reload(self.module)
        self._result = None
        return self

    def __exit__(self, exc_type, exc_val, exc_traceback):
        # Restore default values/methods
        setattr(basic, '_ANSIBLE_ARGS', None)
        setattr(basic.AnsibleModule, 'fail_json', self._real_fail_json)
        setattr(basic.AnsibleModule, 'exit_json', self._real_exit_json)
        # Remove the mock swsscommon module
        _unset_fake_import('swsscommon')
        # Reload the module to remove any global state in the module
        importlib.reload(self.module)
        # As ModuleFailJSON and ModuleExitJSON is used get the result from the module store the result
        # and return True so the exceptions aren't being raised
        if exc_type == ModuleFailJSON:
            self._failed = True
            self._result = exc_val.args[0]
            return True
        elif exc_type == ModuleExitJSON:
            self._failed = False
            self._result = exc_val.args[0]
            return True
        return False
