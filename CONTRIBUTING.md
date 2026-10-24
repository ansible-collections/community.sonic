# Contributing

We welcome bug reports, fixes, documentation improvements, and new maintainers.
Report bugs and request features in the
[issue tracker](https://github.com/ansible-collections/community.sonic/issues).
Include the collection, ansible-core, Python, and SONiC versions, a minimal
playbook, and the expected and actual results. Remove credentials from reports.

Open pull requests against `main`. Add regression tests for behavior changes
and an appropriate YAML fragment under `changelogs/fragments/`. Run the unit,
sanity, documentation, and changelog checks described in [README.md](README.md)
and [MAINTAINING.md](MAINTAINING.md). Integration tests require a KVM-capable host.

Follow the [Ansible contribution guide](https://docs.ansible.com/projects/ansible/latest/community/index.html)
and our [Code of Conduct](CODE_OF_CONDUCT.md), including its reporting process.
Join the [Ansible Forum](https://forum.ansible.com/c/project/collection-development/27)
for collection development questions; use the `collections` tag and mention
`community.sonic` in the topic title.
