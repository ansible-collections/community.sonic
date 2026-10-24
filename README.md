# Ansible collection for SONiC Network Operating System

[![CI](https://github.com/ansible-collections/community.sonic/workflows/CI/badge.svg?event=push)](https://github.com/ansible-collections/community.sonic/actions) [![Codecov](https://img.shields.io/codecov/c/github/ansible-collections/community.sonic)](https://codecov.io/gh/ansible-collections/community.sonic)


<p align="center">
<img src="https://user-images.githubusercontent.com/149442/232787483-7a348ed3-265a-4d5d-8c05-95246a3aa7e9.png" alt="SONiC project logo" />
</p>



## Using this collection

To jump straight to it - this collection is useful for you if you want to manage the configuration of your SONiC switch(es) via Ansible.

An example says more than a thousand words, so here is an example:

```yaml
# set_port_play.yml
---
- name: Connect to a SONiC switch and set properties on a port
  hosts: sonic-sw1.example.com
  gather_facts: false
  tasks:
    - name: Set port description
      community.sonic.sonic_interface_port:
        interface: qsfp1
        description: This is the uplink
        speed: 100G
        fec: rs
        enabled: true
```

```ini
# inventory.ini
[my_sonic_switches]
sonic-sw1.example.com ansible_user=sonic ansible_password=password
```
```bash
$ ansible-playbook -i inventory.ini set_port_play.yml
```

## Code of Conduct

We follow the [Ansible Code of Conduct](https://docs.ansible.com/ansible/devel/community/code_of_conduct.html) in all our interactions within this project.

If you encounter abusive behavior, please refer to the [policy violations](https://docs.ansible.com/ansible/devel/community/code_of_conduct.html#policy-violations) section of the Code for information on how to raise a complaint.

## Communication

Join the [Ansible Forum Get Help category](https://forum.ansible.com/c/help/6) for
Ansible usage questions. Use the existing `collections` tag and include
`community.sonic` in the title. Everyone is welcome to participate.

For SONiC discussions, join the [SONiC Community Matrix](https://matrix.to/#/#sonic-net:matrix.org) room and on the [sonic-dev](https://lists.sonicfoundation.dev/g/sonic-dev) mailing list.


## Contributing to this collection


The content of this collection is made by people like you, a community of individuals collaborating on making the world better through developing automation software.

We welcome new contributors and maintainers.

Any kind of contribution is very welcome.

You don't know how to start? Refer to our [contribution guide](CONTRIBUTING.md)!

We use the following guidelines:

* [CONTRIBUTING.md](CONTRIBUTING.md)
* [REVIEW_CHECKLIST.md](REVIEW_CHECKLIST.md)
* [Ansible Community Guide](https://docs.ansible.com/ansible/latest/community/index.html)
* [Ansible Development Guide](https://docs.ansible.com/ansible/devel/dev_guide/index.html)
* [Ansible Collection Development Guide](https://docs.ansible.com/ansible/devel/dev_guide/developing_collections.html#contributing-to-collections)

### Running tests locally

When developing new features you will want to run the tests to ensure things
are working as they should.

Run these commands from a checkout at
`ansible_collections/community/sonic` (the path layout required by `ansible-test`).
Install a supported `ansible-core` on the controller first. Docker runs the
complete sanity suite across the Python versions supported by that core release.

To run the unit and sanity tests:

```
$ ansible-test units --docker
$ ansible-test sanity --docker
```

To run the full integration suite using a virtual SONiC switch, use a Linux host
with Docker and `/dev/kvm`. The image defaults to `stable-2.21`; pass
`--build-arg ANSIBLE_CORE_REF=stable-2.19` (or another supported branch) to test it.
The SONiC 202605 image is downloaded during the build; `SONIC_BRANCH` and
`SONIC_IMAGE_URL` build arguments select another available image. See
[MAINTAINING.md](MAINTAINING.md) for a separate image cache option.

```
$ docker build -t testbed -f testbed/Dockerfile testbed
$ docker run --device /dev/kvm -ti -w /work/ansible_collections/community/sonic \
    -v "$PWD:/work/ansible_collections/community/sonic" \
    --user "$(id -u):$(id -g)" testbed -- /docker.sh
```

## Collection maintenance

The current maintainers are listed in the [MAINTAINERS](MAINTAINERS) file. If you have questions or need help, feel free to mention them in the proposals.

To learn how to maintain / become a maintainer of this collection, refer to the [Maintainer guidelines](MAINTAINING.md).

## Governance

The process of decision making in this collection is based on discussing and finding consensus among participants.

Every voice is important. If you have something on your mind, create an issue or dedicated discussion and let's discuss it!

## Requirements and supported Ansible versions

This development branch requires `ansible-core >=2.19`. CI covers the maintained
2.19, 2.20, and 2.21 branches, plus `devel`, with sanity, unit, and virtual-switch
integration tests on GitHub Actions. Integration jobs use GitHub-hosted
`ubuntu-24.04` x86 runners with KVM; no self-hosted or Azure runner is needed.
See [maintenance status](MAINTAINING.md) for outstanding infrastructure checks.

Use a controller Python version supported by your selected `ansible-core`.
Modules run on the SONiC host and require Python 3.9 or newer and SONiC's
`swsscommon` Python bindings. Python 3.8 targets are not supported, including
when using `ansible-core 2.19`. Use SSH with the system Python interpreter that
has those bindings installed; these modules do not use `network_cli` or an
HTTP API. The Ansible user needs permission to access SONiC's configuration DB.

The modules update the running configuration database. Persist changes with
SONiC's configuration save procedure if they must survive a reboot.

## Tested with SONiC

 * Release 202211 (historical integration baseline; a fresh VM run is pending)

### Supported connections

 * Only SSH connections supported

### Installing the Collection from Ansible Galaxy

Before using this collection, you need to install it with the Ansible Galaxy command-line tool:

```bash
ansible-galaxy collection install community.sonic
```

You can also include it in a `requirements.yml` file and install it with `ansible-galaxy collection install -r requirements.yml`, using the format:

```yaml
---
collections:
  - name: community.sonic
```

Note that if you install the collection from Ansible Galaxy, it will not be upgraded automatically when you upgrade the `ansible` package.
To upgrade the collection to the latest available version, run the following command:

```bash
$ ansible-galaxy collection install community.sonic --upgrade
```

You can also install a specific version of the collection, for example, if you need to downgrade when something is broken in the latest version (please report an issue in this repository). Use the following syntax to install version `0.1.0`:

```bash
$ ansible-galaxy collection install community.sonic:==0.1.0
```

See [Ansible Using collections](https://docs.ansible.com/projects/ansible/latest/collections_guide/collections_using.html) for more details.

## Release notes

See the [changelog](https://github.com/ansible-collections/community.sonic/tree/main/CHANGELOG.rst).

## Licensing

GNU General Public License v3.0 or later.

See [LICENSE](https://www.gnu.org/licenses/gpl-3.0.txt) to see the full text.
