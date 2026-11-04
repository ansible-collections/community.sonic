================================================
Ansible SONiC community collection Release Notes
================================================

.. contents:: Topics

v0.4.0
======

Release Summary
---------------

First release since 0.3.1. The collection grows from four modules to thirty,
covering device metadata, management interface and VRF, DNS, NTP, features,
sFlow, SNMP, gNMI/telemetry, ports and transceivers, PortChannels, VLANs,
L3 interfaces and loopbacks, VXLAN/EVPN, ACLs, HWSKU installation, saving
the configuration and gathering facts. Modules use short names without a
``sonic_`` prefix; ``sonic_interface_port`` redirects to ``interface_port``.
ansible-core 2.19 or newer is required.

Minor Changes
-------------

- Add ``plugins/module_utils/acl.py`` with the shared ACL layout detection and ``STATE_DB`` status helpers. Before changing a table or rule the modules delete its ``STATE_DB`` status entry, so the status check after the write cannot accept the status of the previous configuration.
- Add a dict-backed fake ``swsscommon`` and ``run_module`` pytest fixtures under ``tests/unit`` so module unit tests can seed CONFIG_DB content and assert on writes without a SONiC device.
- Add the ``acl_rule`` module to manage the rules of an ACL table declaratively, routing rules to the IPv4 or IPv6 table of a split policy and checking the ``STATE_DB`` rule status after writing (https://github.com/ansible-collections/community.sonic/issues/35).
- Add the ``acl_table`` module to manage ``ACL_TABLE`` entries, with a ``family_mode`` option that lays a dual-stack policy out as one ``L3V4V6`` table or as ``L3`` plus ``L3V6`` tables depending on what the ASIC supports, and that verifies the result through the ``STATE_DB`` status orchagent publishes (https://github.com/ansible-collections/community.sonic/issues/35).
- Add the ``community.sonic.plugins.module_utils.config_db`` helper layer with a ``ConfigDB`` wrapper (check-mode aware reads and writes, ``ensure_entry``/``ensure_absent`` with before/after diffs), compound key helpers, port alias resolution, interface type classification, boolean-to-string helpers and the standard result builder for writing new modules.
- Add the ``dns_nameserver`` module to manage the static DNS nameservers in the ``DNS_NAMESERVER`` table, either one address at a time or as an optionally exclusive list (https://github.com/ansible-collections/community.sonic/issues/28).
- Add the ``feature`` module to enable or disable SONiC features (containers) and manage their ``auto_restart`` and ``high_mem_alert`` settings through the ``FEATURE`` table (https://github.com/ansible-collections/community.sonic/issues/25).
- Add the ``gnmi_server``, ``gnmi_client_cert`` and ``telemetry_client`` modules to manage the gNMI dial-in server (``GNMI`` or legacy ``TELEMETRY`` table, detected from the ``FEATURE`` table), client certificate to role mappings (``GNMI_CLIENT_CERT``) and the gNMI dial-out client (``TELEMETRY_CLIENT`` global settings, destination groups and subscriptions) (https://github.com/ansible-collections/community.sonic/issues/34).
- Add the ``hwsku`` module to install a (custom) HWSKU directory, select the HWSKU in ``/etc/sonic/sonic-environment`` and the saved ``config_db.json`` and regenerate the ``PORT`` table for it, returning ``reboot_required`` so the play decides when to reboot (https://github.com/ansible-collections/community.sonic/issues/30).
- Add the ``interface_ip`` module to manage IPv4 and IPv6 addresses on Ethernet, PortChannel, VLAN and Loopback interfaces (``INTERFACE``, ``PORTCHANNEL_INTERFACE``, ``VLAN_INTERFACE`` and ``LOOPBACK_INTERFACE``), creating the interface's L3 entry with the first address and optionally removing it with the last one.
- Add the ``loopback`` module to create and remove ``LoopbackN`` interfaces and bind them to a VRF (``LOOPBACK_INTERFACE``).
- Add the ``ntp``, ``ntp_server`` and ``ntp_key`` modules to manage the global NTP settings (``NTP|global``), the NTP servers and pools (``NTP_SERVER``, one at a time or as an optionally exclusive list) and the NTP authentication keys (``NTP_KEY``) (https://github.com/ansible-collections/community.sonic/issues/47).
- Add the ``portchannel`` and ``portchannel_member`` modules to manage link aggregation groups through the ``PORTCHANNEL`` and ``PORTCHANNEL_MEMBER`` tables (https://github.com/ansible-collections/community.sonic/issues/22).
- Add the ``sflow``, ``sflow_collector`` and ``sflow_session`` modules to manage the global sFlow state (``SFLOW|global``), collectors including the collector VRF (``SFLOW_COLLECTOR``) and per-interface sampling sessions (``SFLOW_SESSION``), with port alias support for sessions and the agent interface (https://github.com/ansible-collections/community.sonic/issues/23).
- Add the ``snmp_community`` module to manage SNMP community strings in the ``SNMP_COMMUNITY`` table; the community string is ``no_log`` and kept out of the result and diff (https://github.com/ansible-collections/community.sonic/issues/24).
- Add the ``snmp`` module to manage the SNMP agent location and contact in the ``SNMP`` table (https://github.com/ansible-collections/community.sonic/issues/24).
- Add the ``sonic_facts`` module that gathers SONiC device facts (platform, HWSKU, ASIC type, hostname, MAC address, software version and build, management VRF state, feature states) under ``ansible_facts.sonic``, with optional ``config_db`` and ``saved_config_db`` subsets for the complete running configuration database and the parsed ``/etc/sonic/config_db.json`` (https://github.com/ansible-collections/community.sonic/issues/33).
- Add the ``vxlan_tunnel`` and ``vxlan_map`` modules to manage the VXLAN tunnel endpoint (``VXLAN_TUNNEL``), the EVPN NVO bound to it (``VXLAN_EVPN_NVO``) and VLAN-to-VNI maps (``VXLAN_TUNNEL_MAP``), enforcing the single VTEP and NVO rule and removing maps, NVO and tunnel in order with ``force`` (https://github.com/ansible-collections/community.sonic/issues/32).
- CI now covers ansible-core 2.19, 2.20, 2.21 and devel, with daily runs and pinned GitHub Actions maintained by Dependabot.
- Document how to write a module, the proposed short module naming convention and the expected integration target layout in CONTRIBUTING.md.
- Move virtual-switch integration tests from Azure Pipelines to GitHub-hosted KVM runners, require them in the GitHub check status, and retain failure diagnostics. The testbed uses Debian Trixie, native QEMU SSH forwarding, and bounded boot and image-download waits.
- config_save - new module that persists the running CONFIG_DB to ``/etc/sonic/config_db.json`` with ``config save -y``, reporting ``changed`` only when the file differs from the running configuration, with check mode, a table-level diff, an optional timestamped backup and ``return_config`` to read the startup configuration (https://github.com/ansible-collections/community.sonic/issues/29).
- device_metadata - new module to manage the switch identity fields in ``DEVICE_METADATA|localhost`` (hostname, timezone, system MAC, device type, BGP ASN, default BGP and PFC watchdog status, buffer model and synchronous mode) by merging into the existing entry; ``hwsku`` and ``platform`` can be asserted but not changed (https://github.com/ansible-collections/community.sonic/issues/27).
- get_entry, sonic_interface_port, vlan, vlan_member - use the shared ``config_db`` module_utils; options, results and diff output are unchanged.
- interface_port - add the ``laser_frequency``, ``tx_power`` and ``dom_polling`` options to manage the transceiver settings (``laser_freq``, ``tx_power`` and ``dom_polling`` fields of the ``PORT`` table) that tunable and coherent optics need; ``xcvrd`` applies them to the module. Omitting an option leaves the field untouched, ``laser_frequency=0``, ``tx_power=0`` and ``dom_polling=default`` remove it (https://github.com/ansible-collections/community.sonic/issues/21).
- interface_port - the ``sonic_interface_port`` module has been renamed to ``interface_port``; modules in this collection use short names without a ``sonic_`` prefix because the fully qualified name already carries the collection name.
- mgmt_interface - new module managing management interface addresses and gateways (``MGMT_INTERFACE``) per address and the management port settings (``MGMT_PORT``) (https://github.com/ansible-collections/community.sonic/issues/26).
- mgmt_vrf - new module enabling or disabling the management VRF (``MGMT_VRF_CONFIG``) (https://github.com/ansible-collections/community.sonic/issues/26).
- tests - the fake ``swsscommon`` connector now returns ``['']`` for an empty list field, as the real ``ConfigDBConnector`` does.
- vlan and vlan_member now return before/after diffs, including in check mode.
- vlan_member - accept PortChannels and port aliases as ``interface``, return the resolved ``interface`` name and fail with a clear message for unknown ports (https://github.com/ansible-collections/community.sonic/issues/22).

Breaking Changes / Porting Guide
--------------------------------

- The collection now requires ansible-core 2.19 or newer (``requires_ansible`` in ``meta/runtime.yml``). Controllers on older ansible-core releases must stay on community.sonic 0.3.1.

Deprecated Features
-------------------

- sonic_interface_port - the module name is deprecated and redirects to ``community.sonic.interface_port``. The redirect will be removed in community.sonic 2.0.0; use ``community.sonic.interface_port`` instead.

Bugfixes
--------

- Correct documentation site template URLs and document target Python and swsscommon requirements.
- module_utils config_db - replacing an entry (``set_entry``, used by every module that owns its entries) now runs the ``HSET`` of the new fields and the ``HDEL`` of the removed ones in a single redis transaction. swsscommon issues them as separate commands, and daemons that re-read the entry on every keyspace event (orchagent, hostcfgd) could evaluate the intermediate entry that still carried the removed fields, for example rejecting an ACL rule as invalid before the final write arrived.
- sonic_interface_port - ``enabled=false`` no longer raises KeyError on a port without ``admin_status`` in CONFIG_DB, such as a factory-default configuration or a port that is already disabled, and is idempotent in that case. Disabling now writes ``admin_status=down`` instead of removing the field, which SONiC ignores for an already configured port (https://github.com/ansible-collections/community.sonic/issues/17).
- sonic_interface_port - updating a port without a configured speed no longer raises TypeError.
- vlan - compare the VLAN ID as a database string so applying an existing VLAN is idempotent.

New Modules
-----------

- acl_rule - Configure SONiC ACL rules
- acl_table - Configure SONiC ACL tables
- config_save - Persist the running SONiC configuration to the startup configuration file
- device_metadata - Configure SONiC device metadata (hostname, timezone, system MAC, ...)
- dns_nameserver - Configure SONiC DNS nameservers
- feature - Enable or disable SONiC features (containers)
- gnmi_client_cert - Authorise gNMI clients by certificate common name on SONiC
- gnmi_server - Configure the SONiC gNMI (streaming telemetry) server
- hwsku - Install and select the hardware SKU (HWSKU) of a SONiC switch
- interface_ip - Configure IP addresses on SONiC L3 interfaces
- loopback - Configure SONiC loopback interfaces
- mgmt_interface - Configure the SONiC management interface
- mgmt_vrf - Enable or disable the SONiC management VRF
- ntp - Configure global NTP settings on SONiC
- ntp_key - Configure NTP authentication keys on SONiC
- ntp_server - Configure NTP servers on SONiC
- portchannel - Configure SONiC PortChannels (LAG)
- portchannel_member - Configure SONiC PortChannel (LAG) members
- sflow - Configure global sFlow settings on SONiC
- sflow_collector - Configure sFlow collectors on SONiC
- sflow_session - Configure per\-interface sFlow sessions on SONiC
- snmp - Configure the SONiC SNMP agent location and contact
- snmp_community - Configure SONiC SNMP community strings
- sonic_facts - Gather facts about a SONiC device
- telemetry_client - Configure the SONiC gNMI dial\-out (push) telemetry client
- vxlan_map - Configure VLAN\-to\-VNI maps on a SONiC VXLAN tunnel
- vxlan_tunnel - Configure the VXLAN tunnel endpoint (VTEP) and EVPN NVO on SONiC

v0.3.1
======

Minor Changes
-------------

- port - Fix documentation

v0.3.0
======

Major Changes
-------------

- port - Module now handles FEC
- port - Module now handles diff mode

v0.2.0
======

New Modules
-----------

- get_entry - Get table/entry from SONiC configuration database
- vlan - Configure a SONiC VLANs
- vlan_member - Configure a SONiC VLAN port memberships

v0.1.0
======

Release Summary
---------------

Initial release, support for setting and clearing interface description.
