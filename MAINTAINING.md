# Maintaining this collection

Refer to the [Maintainer guidelines](https://github.com/ansible/community-docs/blob/main/maintaining.rst).

## Generating changelogs

```
# Update galaxy.yml before this
python3 -m venv /tmp/antsibull-changelog
/tmp/antsibull-changelog/bin/pip install antsibull-changelog
/tmp/antsibull-changelog/bin/antsibull-changelog lint
/tmp/antsibull-changelog/bin/antsibull-changelog release
```
