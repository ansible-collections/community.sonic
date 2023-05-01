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
- name: Connect to a SONiC swich and set properties on a port
  hosts: sonic-sw1.example.com
  gather_facts: false
  tasks:
    - name: Set port description
      community.sonic.sonic_interface_port:
        interface: qsfp1
        description: This is the uplink
        speed: 100G
        enabled: True
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

We mostly hang out in the [SONiC Community Matrix](https://matrix.to/#/#sonic-net:matrix.org) room and on the [sonic-dev](https://lists.sonicfoundation.dev/g/sonic-dev) mailinglist.


## Contributing to this collection


<!--Describe how the community can contribute to your collection. At a minimum, fill up and include the CONTRIBUTING.md file containing how and where users can create issues to report problems or request features for this collection. List contribution requirements, including preferred workflows and necessary testing, so you can benefit from community PRs. If you are following general Ansible contributor guidelines, you can link to - [Ansible Community Guide](https://docs.ansible.com/ansible/devel/community/index.html). List the current maintainers (contributors with write or higher access to the repository). The following can be included:-->

The content of this collection is made by people like you, a community of individuals collaborating on making the world better through developing automation software.

We are actively accepting new contributors.

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

To run the unit and sanity tests:

```
$ ansible-test units --docker
$ ansible-test sanity --docker
```

To run the full integration suite using a virtual SONiC switch:

```
$ docker build -t testbed -f testbed/Dockerfile testbed
$ docker run --device /dev/kvm -ti -w /work/ansible_collections/community/sonic \
    -v $PWD:/work/ansible_collections/community/sonic --user 1000:1000 testbed /docker.sh
```

## Collection maintenance

The current maintainers are listed in the [MAINTAINERS](MAINTAINERS) file. If you have questions or need help, feel free to mention them in the proposals.

To learn how to maintain / become a maintainer of this collection, refer to the [Maintainer guidelines](MAINTAINING.md).

## Governance

The process of decision making in this collection is based on discussing and finding consensus among participants.

Every voice is important. If you have something on your mind, create an issue or dedicated discussion and let's discuss it!

## Tested with Ansible

 * Ansible 2.12
 * Ansible 2.13
 * Ansible 2.14
 * Ansible 2.15

## Tested with SONiC

 * Release 202211

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

See [Ansible Using collections](https://docs.ansible.com/ansible/devel/user_guide/collections_using.html) for more details.

## Release notes

See the [changelog](https://github.com/ansible-collections/community.sonic/tree/main/CHANGELOG.rst).

## Licensing

GNU General Public License v3.0 or later.

See [LICENSE](https://www.gnu.org/licenses/gpl-3.0.txt) to see the full text.
