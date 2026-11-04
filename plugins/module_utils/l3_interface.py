# -*- coding: utf-8 -*-
#
# GNU General Public License v3.0+ (see https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

"""Helpers shared by the L3 interface modules (``loopback``, ``interface_ip``).

SONiC keeps one table per interface kind (``INTERFACE``,
``PORTCHANNEL_INTERFACE``, ``VLAN_INTERFACE``, ``LOOPBACK_INTERFACE``, see
:func:`config_db.l3_interface_table`). Each table holds a *parent* entry named
after the interface (``Loopback0``) that carries interface wide settings such
as ``vrf_name``, plus one empty ``<interface>|<prefix>`` entry per IP address.
"""

from __future__ import (absolute_import, division, print_function)
__metaclass__ = type

import ipaddress
import re

from ansible_collections.community.sonic.plugins.module_utils.config_db import (
    ConfigDBError,
    KEY_SEPARATOR,
    split_key,
)

#: ``config loopback add`` accepts ``Loopback0`` to ``Loopback999``.
_LOOPBACK_RE = re.compile(r'^Loopback(\d{1,3})$')


class InvalidAddressError(ConfigDBError):
    """Raised when an IP prefix is malformed or not usable as an interface address."""


class InvalidLoopbackNameError(ConfigDBError):
    """Raised when a loopback interface name is not ``Loopback<N>``."""


def validate_loopback_name(name):
    """Return ``name`` if it is a valid ``Loopback<N>`` (N = 0..999) interface name, else raise :class:`InvalidLoopbackNameError`."""
    name = str(name)
    if _LOOPBACK_RE.match(name) is None:
        raise InvalidLoopbackNameError(
            'invalid loopback interface name "%s"; expected Loopback<N> with N between 0 and 999, for example Loopback0' % name)
    return name


def normalize_prefix(address):
    """Validate an interface address written as ``<ip>/<prefixlen>`` and return it in canonical form.

    The canonical form is what ``config interface ip add`` stores
    (``str(ipaddress.ip_interface(address))``), so IPv6 addresses are
    compressed and the stored key compares equal regardless of how the user
    spelt the address. Raises :class:`InvalidAddressError` for addresses
    without a prefix length and for addresses that cannot be assigned to an
    interface (multicast, unspecified, and for IPv4 prefixes shorter than /31
    the network and broadcast addresses).
    """
    text = str(address).strip()
    if '/' not in text:
        raise InvalidAddressError('address "%s" must include a prefix length, for example 192.0.2.1/31' % address)
    try:
        iface = ipaddress.ip_interface(text)
    except ValueError as e:
        raise InvalidAddressError('address "%s" is not a valid IP prefix: %s' % (address, e))
    ip = iface.ip
    if ip.is_multicast:
        raise InvalidAddressError('address "%s" is a multicast address' % address)
    if ip.is_unspecified:
        raise InvalidAddressError('address "%s" is the unspecified address' % address)
    if iface.version == 4 and iface.network.prefixlen < 31:
        if ip == iface.network.network_address:
            raise InvalidAddressError('address "%s" is the network address of %s' % (address, iface.network))
        if ip == iface.network.broadcast_address:
            raise InvalidAddressError('address "%s" is the broadcast address of %s' % (address, iface.network))
    return str(iface)


def address_keys(db, table, interface):
    """Return the sorted ``<interface>|<prefix>`` keys of ``interface`` in ``table``."""
    prefix = interface + KEY_SEPARATOR
    return sorted(k for k in db.get_keys(table) if k.startswith(prefix))


def addresses_of(db, table, interface):
    """Return the sorted list of prefixes configured on ``interface`` in ``table``."""
    return [split_key(k)[1] for k in address_keys(db, table, interface)]


def member_of(db, interface):
    """Return the VLAN or PortChannel that ``interface`` is a member of, or ``None``.

    SONiC refuses IP addresses on an interface that is a member of a VLAN or a
    PortChannel, so the modules fail early with a clear message instead.
    """
    for table in ('PORTCHANNEL_MEMBER', 'VLAN_MEMBER'):
        for key in db.get_keys(table):
            parts = split_key(key)
            if len(parts) == 2 and parts[1] == interface:
                return parts[0]
    return None
