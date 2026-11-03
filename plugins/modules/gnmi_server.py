#!/usr/bin/python
#
# GNU General Public License v3.0+ (see https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import (absolute_import, division, print_function)
__metaclass__ = type


DOCUMENTATION = r'''
---
module: gnmi_server
short_description: Configure the SONiC gNMI (streaming telemetry) server
version_added: "0.4.0"
description:
  - Manage the gNMI server settings of a SONiC switch, that is the C(gnmi)
    and C(certs) entries of the C(GNMI) table (or of the legacy C(TELEMETRY)
    table on images that still run the C(telemetry) container).
  - The C(gnmi) entry holds the listening port, authentication settings and
    log level; the C(certs) entry points at the TLS certificate and key files
    on the switch. The files themselves are best managed with
    M(ansible.builtin.copy); this module only records their paths.
  - Only the options that are given are written; other fields of the entries
    are left as they are. An empty string removes a certificate path.
  - By default the module picks the table from the C(FEATURE) table, C(GNMI)
    when the C(gnmi) feature exists and C(TELEMETRY) otherwise, which is what
    the C(gnmi) and C(telemetry) containers read respectively. Use O(table) to
    override the detection.
  - The gNMI container reads these settings when it starts, so changes take
    effect after C(systemctl restart gnmi) (or C(telemetry)). Register the
    result and restart the service in a handler. Without certificates the
    server falls back to plain text on C(127.0.0.1) only.
  - Client certificate to role mappings are managed with
    M(community.sonic.gnmi_client_cert); the dial-out client with
    M(community.sonic.telemetry_client).
extends_documentation_fragment:
  - community.sonic.attributes
attributes:
  check_mode:
    support: full
  diff_mode:
    support: full
options:
  table:
    description:
      - The CONFIG_DB table to write.
      - V(GNMI) is read by the C(gnmi) container (SONiC 202311 and later),
        V(TELEMETRY) by the legacy C(telemetry) container.
      - When omitted, V(GNMI) is used if the C(gnmi) feature exists on the
        device and V(TELEMETRY) otherwise.
    type: str
    choices: [GNMI, TELEMETRY]
  port:
    description:
      - TCP port the gNMI server listens on.
      - SONiC defaults to V(8080) when nothing is configured; recent images
        ship V(50052) in their default configuration.
    type: int
  client_auth:
    description:
      - Whether clients must present a TLS client certificate.
      - V(false) starts the server with C(--allow_no_client_auth).
    type: bool
  user_auth:
    description:
      - Authentication methods the server accepts, written as a comma separated
        list to the C(user_auth) field.
      - V(password) and V(jwt) authenticate against the local user database,
        V(cert) authorises by client certificate using the
        C(GNMI_CLIENT_CERT) table (see M(community.sonic.gnmi_client_cert)),
        V(none) disables authentication and cannot be combined with the others.
      - The gNMI daemon accepts several methods at once; SONiC's YANG model
        only validates a single value, so YANG-checked tooling (C(config
        replace), generic config updater) may reject a list.
      - When no C(user_auth) is configured at all, recent images default to
        V(cert).
    type: list
    elements: str
    choices: [password, jwt, cert, none]
  log_level:
    description: Verbosity of the gNMI daemon, V(0) to V(100). SONiC defaults to V(2).
    type: int
  save_on_set:
    description: Whether the running configuration is saved to C(config_db.json) after every gNMI C(Set).
    type: bool
  enable_crl:
    description: Whether client certificates are checked against a certificate revocation list.
    type: bool
  crl_expire_duration:
    description: How long, in seconds, a downloaded certificate revocation list is cached.
    type: int
  ca_cert:
    description:
      - Path on the switch of the CA certificate used to verify client certificates.
      - Written to the C(ca_crt) field of the C(certs) entry. An empty string removes it.
    type: str
  server_cert:
    description:
      - Path on the switch of the server certificate.
      - Written to the C(server_crt) field. An empty string removes it; the
        daemon needs both O(server_cert) and O(server_key) to serve TLS.
    type: str
  server_key:
    description:
      - Path on the switch of the server private key.
      - Written to the C(server_key) field. An empty string removes it.
    type: str
  state:
    description:
      - V(present) applies the given options.
      - V(absent) removes both the C(gnmi) and the C(certs) entries, so the
        server starts with SONiC's built-in defaults.
    type: str
    choices: [present, absent]
    default: present
notes:
  - SONiC's YANG models expect certificate paths ending in C(.cer) and keys
    ending in C(.key). The daemon itself accepts any path, but YANG-validated
    tooling may reject other extensions.
  - With the management VRF enabled the server binds in the management VRF
    automatically; no VRF option is needed.
  - At least one option besides O(table) must be given with O(state=present).
author:
  - Christian Svensson (@bluecmd)
'''

EXAMPLES = r'''
- name: gNMI server with mutual TLS, authorising collectors by client certificate
  community.sonic.gnmi_server:
    port: 50052
    client_auth: true
    user_auth: [cert]
    log_level: 2
    ca_cert: /etc/sonic/telemetry/ca.cer
    server_cert: /etc/sonic/telemetry/server.cer
    server_key: /etc/sonic/telemetry/server.key
  notify: Restart gnmi

- name: Allow password and JWT logins as well
  community.sonic.gnmi_server:
    user_auth: [password, jwt, cert]

- name: Point an older image at the legacy TELEMETRY table explicitly
  community.sonic.gnmi_server:
    table: TELEMETRY
    port: 8080
    client_auth: false

- name: Forget the certificate paths, keep the other settings
  community.sonic.gnmi_server:
    ca_cert: ''
    server_cert: ''
    server_key: ''

- name: Remove the gNMI server configuration altogether
  community.sonic.gnmi_server:
    state: absent

# A handler to apply the settings; the container only reads them at start
- name: Restart gnmi
  ansible.builtin.systemd_service:
    name: gnmi
    state: restarted
  become: true
'''

RETURN = r'''
table:
  description: The CONFIG_DB table that was used, C(GNMI) or C(TELEMETRY).
  type: str
  returned: always
  sample: GNMI
diff:
  description: The C(gnmi) and C(certs) entries of the table before and after the change; an absent entry is C({}).
  type: dict
  returned: always
  sample:
    before: {gnmi: {port: '8080'}, certs: {}}
    after: {gnmi: {port: '50052', client_auth: 'true'}, certs: {server_crt: /etc/sonic/telemetry/server.cer}}
'''

from ansible.module_utils.basic import AnsibleModule
from ansible_collections.community.sonic.plugins.module_utils.config_db import (
    ConfigDB, ConfigDBError, EntryChange, build_result)

TABLES = ('GNMI', 'TELEMETRY')
SERVER_KEY = 'gnmi'
CERTS_KEY = 'certs'

USER_AUTH_CHOICES = ('password', 'jwt', 'cert', 'none')

MIN_LOG_LEVEL = 0
MAX_LOG_LEVEL = 100

#: Module option -> ``certs`` entry field.
CERT_FIELDS = (
    ('ca_cert', 'ca_crt'),
    ('server_cert', 'server_crt'),
    ('server_key', 'server_key'),
)

#: Module options written unchanged (apart from normalisation) to the ``gnmi`` entry.
SERVER_FIELDS = ('port', 'client_auth', 'log_level', 'save_on_set', 'enable_crl', 'crl_expire_duration')


def detect_table(feature_keys):
    """Return the table the running image reads: ``GNMI`` if the ``gnmi`` feature exists, else ``TELEMETRY``.

    The ``gnmi`` container renders its startup arguments from the ``GNMI``
    table, the older ``telemetry`` container from ``TELEMETRY``.
    """
    return 'GNMI' if 'gnmi' in feature_keys else 'TELEMETRY'


def join_user_auth(methods):
    """Return the comma separated ``user_auth`` value for a list of methods, without duplicates.

    Raises ``ValueError`` when ``none`` is combined with other methods or the
    list is empty.
    """
    result = []
    for method in methods:
        if method not in result:
            result.append(method)
    if not result:
        raise ValueError('user_auth must list at least one method')
    if 'none' in result and len(result) > 1:
        raise ValueError('user_auth "none" cannot be combined with other methods')
    return ','.join(result)


def build_server_entry(port=None, client_auth=None, user_auth=None, log_level=None,
                       save_on_set=None, enable_crl=None, crl_expire_duration=None):
    """Return the fields to merge into the ``gnmi`` entry; ``user_auth`` is already joined."""
    desired = {}
    for field, value in (('port', port), ('client_auth', client_auth), ('user_auth', user_auth),
                         ('log_level', log_level), ('save_on_set', save_on_set),
                         ('enable_crl', enable_crl), ('crl_expire_duration', crl_expire_duration)):
        if value is not None:
            desired[field] = value
    return desired


def build_certs_entry(ca_cert=None, server_cert=None, server_key=None):
    """Return the fields to merge into the ``certs`` entry; an empty string maps to ``None`` (remove)."""
    desired = {}
    for option, field in CERT_FIELDS:
        value = {'ca_cert': ca_cert, 'server_cert': server_cert, 'server_key': server_key}[option]
        if value is not None:
            desired[field] = value or None
    return desired


def merge_entry(db, table, key, desired):
    """Merge ``desired`` into an entry and return an ``EntryChange``.

    Unlike ``ConfigDB.ensure_entry`` this never creates an entry just to
    remove fields from it: when nothing is to be set and the entry does not
    exist (clearing certificate paths that were never configured) it is a
    no-op.
    """
    if not any(value is not None for value in desired.values()) and not db.has_entry(table, key):
        return EntryChange(False, {}, {})
    return db.ensure_entry(table, key, desired, exclusive=False)


def run_module():
    module_args = dict(
        table=dict(type='str', choices=list(TABLES)),
        port=dict(type='int'),
        client_auth=dict(type='bool'),
        user_auth=dict(type='list', elements='str', choices=list(USER_AUTH_CHOICES)),
        log_level=dict(type='int'),
        save_on_set=dict(type='bool'),
        enable_crl=dict(type='bool'),
        crl_expire_duration=dict(type='int'),
        ca_cert=dict(type='str'),
        server_cert=dict(type='str'),
        server_key=dict(type='str', no_log=False),  # a file path, not the key itself
        state=dict(type='str', default='present', choices=['present', 'absent']),
    )

    settings = SERVER_FIELDS + ('user_auth',) + tuple(option for option, dummy in CERT_FIELDS)
    module = AnsibleModule(
        argument_spec=module_args,
        supports_check_mode=True,
        required_if=(('state', 'present', settings, True),),
    )
    params = module.params

    port = params['port']
    if port is not None and not (1 <= port <= 65535):
        module.fail_json(msg='port must be between 1 and 65535, got %d' % port)
    log_level = params['log_level']
    if log_level is not None and not (MIN_LOG_LEVEL <= log_level <= MAX_LOG_LEVEL):
        module.fail_json(msg='log_level must be between %d and %d, got %d' % (MIN_LOG_LEVEL, MAX_LOG_LEVEL, log_level))
    crl_expire_duration = params['crl_expire_duration']
    if crl_expire_duration is not None and crl_expire_duration < 0:
        module.fail_json(msg='crl_expire_duration must not be negative, got %d' % crl_expire_duration)
    user_auth = None
    if params['user_auth'] is not None:
        try:
            user_auth = join_user_auth(params['user_auth'])
        except ValueError as e:
            module.fail_json(msg=str(e))

    db = ConfigDB(module).connect()
    try:
        table = params['table'] or detect_table(db.get_keys('FEATURE'))
        if params['state'] == 'absent':
            server = db.ensure_absent(table, SERVER_KEY)
            certs = db.ensure_absent(table, CERTS_KEY)
        else:
            server_desired = build_server_entry(port, params['client_auth'], user_auth, log_level,
                                                params['save_on_set'], params['enable_crl'], crl_expire_duration)
            certs_desired = build_certs_entry(params['ca_cert'], params['server_cert'], params['server_key'])
            server = merge_entry(db, table, SERVER_KEY, server_desired)
            certs = merge_entry(db, table, CERTS_KEY, certs_desired)
    except ConfigDBError as e:
        module.fail_json(msg=str(e))

    changed = server.changed or certs.changed
    before = {SERVER_KEY: server.before, CERTS_KEY: certs.before}
    after = {SERVER_KEY: server.after, CERTS_KEY: certs.after}
    module.exit_json(**build_result(changed, before, after, table=table))


def main():
    run_module()


if __name__ == '__main__':
    main()
