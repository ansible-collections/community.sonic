# Maintaining this collection

Refer to the [Maintainer guidelines](https://docs.ansible.com/projects/ansible/latest/community/maintainers_guidelines.html).

## Generating changelogs

```
# Update galaxy.yml before this
python3 -m venv /tmp/antsibull-changelog
/tmp/antsibull-changelog/bin/pip install antsibull-changelog
/tmp/antsibull-changelog/bin/antsibull-changelog lint
/tmp/antsibull-changelog/bin/antsibull-changelog release
```

## Upstream requirements audit (2026-10-24)

Use the current [collection requirements](https://docs.ansible.com/projects/ansible/latest/community/collection_contributors/collection_requirements.html)
and [core support matrix](https://docs.ansible.com/projects/ansible/latest/reference_appendices/release_and_maintenance.html),
not the archived `ansible-collections/overview` repository. Track
[News for Maintainers](https://forum.ansible.com/tag/news-for-maintainers) and join
the [Collection Maintainers group](https://forum.ansible.com/g/Collection_Maintainers).
The [old Google Groups are read-only](https://forum.ansible.com/t/important-ansible-google-group-moving-to-ansible-forum/38854); use the Forum for Ansible discussions.
The [2.20 import deprecations](https://forum.ansible.com/t/deprecation-warnings-in-ansible-core-2-20/44741)
were checked: this collection does not import `ansible.module_utils.six`,
`ansible.module_utils._text`, or `ansible.module_utils.common._collections_compat`.

| Upstream request | Repository response | Remaining verification |
| --- | --- | --- |
| Sanity and existing tests for all supported core branches | GitHub sanity, unit, and integration matrices cover 2.19, 2.20, 2.21; runtime minimum is 2.19 | Run hosted GitHub checks before release |
| [March 2026: test `devel` or `milestone`](https://forum.ansible.com/t/action-required-for-ansible-package-included-collections-ci-add-test-runs-against-devel-or-milestone-branch-of-ansible-core/45599) | `devel` is in the GitHub test and integration matrices; daily schedules run even without commits | Monitor failures and update the matrix as branches reach EOL |
| Current Ansible Forum communication links | README and contributor guide link to Get Help and collection development, using the existing `collections` tag | Maintainers should join the group and subscribe to news |
| [Check Azure is still working (#16)](https://github.com/ansible-collections/community.sonic/issues/16) | Azure configuration retired; VM integration moves to GitHub-hosted KVM runners with daily runs | Verify a passing GitHub integration run and retire the old required Azure status |
| Retired Debian Bullseye test images | Testbed uses Debian Trixie with a controller Python suitable for supported core releases | Build and boot the virtual switch on the integration runner |
| No unexplained sanity ignores | Fixed script shebangs and removed obsolete ignores | Keep new ignores justified individually if ever needed |
| Collection docs and packaging | Fixed template links, documented target requirements, lint/build checks in CI, excluded CI/editor files from artifacts | Check the release artifact and Galaxy metadata |

Initial infrastructure audit on 2026-10-24 (before GitHub migration):

* Both GitHub workflows report `disabled_inactivity`. Re-enable them after merging
  the refresh; updating workflow source alone does not prove scheduled runs work.
  See the migration section below for the subsequent enablement.
* Azure pipeline 7 exists under `kamelnetworks`, not Ansible's shared organization.
  [Run 709](https://dev.azure.com/kamelnetworks/53a5c7e8-3f52-4611-a688-a61ab05a4216/_build/results?buildId=709)
  failed with exit 137; Azure identified an out-of-memory failure. Run 713 has
  been `notStarted` since 2026-10-19. Check the pool's agent health and available
  RAM explained why the Azure setup was retired in favor of GitHub Actions.
* The old 202211 SONiC VS query returns no retained successful builds. The new
  default is 202605, with `SONIC_BRANCH` and `SONIC_IMAGE_URL` overrides; image
  discovery fails clearly when artifacts expire. A fresh VM run is required
  before claiming this as a tested SONiC release.
* Merge commits and rebase merges are disabled, squash merges are enabled, and
  GitHub Discussions is disabled. Main requires linear history and the `check`
  and `ansible-collections.community.sonic` statuses. `enforce_admins` is false;
  the upstream requirement to prevent bypasses still needs an administrator's
  review. No repository settings were changed during the source refresh.

The old Azure testbed is replaced by GitHub Actions. Issue #16 can be resolved
once the GitHub integration matrix has passed and the old Azure merge requirement
has been removed. The custom testbed uses Debian Trixie, current core branches,
8 GiB VM RAM, and bounded boot waiting. `SONIC_MEMORY_MIB` and
`SONIC_BOOT_TIMEOUT` allow local tuning.

The collection is still version 0.3.1. The refresh is unreleased. Dropping older
ansible-core support is a breaking change and must be released in a major
version (plan 1.0.0). Do not publish this checkout as another 0.3.1 artifact.
Ansible package inclusion also requires a published version of at least 1.0.0
and an inclusion review; this audit does not claim package inclusion.


## Validation and release

From the collection checkout, run:

```sh
ansible-test sanity --docker
ansible-test units --docker
antsibull-docs lint-collection-docs .
antsibull-changelog lint
ansible-galaxy collection build --output-path /tmp/collection-build
```

Repeat sanity and units with each supported core branch and `devel`, and run the
GitHub integration matrix on hosted x86 runners. Docker supplies the complete supported
Python matrix; a local `--venv --python 3.12` run covers only Python 3.12.
Review all scheduled failures regularly and keep the runtime minimum, README,
GitHub sanity/unit matrix, and integration matrix consistent.

Before releasing, complete the infrastructure checks above, choose the major
release version in `galaxy.yml`, generate and review the changelog, run release
checks, tag that exact source version, and build/publish the matching artifact.

For repeated local runs, avoid embedding the large VS image in each controller
image. Download it once with `SONIC_IMAGE_PATH=/path/to/sonic-vs.img
./testbed/download-image.sh`, build with `--build-arg DOWNLOAD_SONIC_IMAGE=false`,
and mount that file read-only at `/opt/sonic-vs.img` when starting the container.
QEMU's snapshot mode keeps the source image unchanged.

## Local refresh validation (2026-10-24)

Sanity and 45 unit cases pass on Python 3.12 with ansible-core 2.19.14,
2.20.10, and 2.21.5, and on Python 3.13 with devel 2.23.0.dev0 at
`4761c59c9639ff70d4db2b91b7361e121d482301`. These are local single-interpreter
runs; the hosted Docker Python matrix still needs to run.
Documentation and changelog linting, ShellCheck, collection build/install, and
installed module discovery pass. The Debian Trixie controller image builds with
`stable-2.21`. Downloader smoke checks verify complete transfers, rejected
truncated gzip streams, preservation of a cached image, and partial-file cleanup.

The fresh SONiC 202605 image transfer for build 1255550 stalled near completion,
then failed with a connection reset and an unexpected gzip EOF. The partial image
was removed. VM integration tests did not complete; no passing VM result is
claimed. The downloader now bounds stalled transfers and atomically publishes
only complete images. Re-run with a complete artifact or a retained image via
`SONIC_IMAGE_URL` before release. No changes have been pushed or published.

## GitHub Actions migration

GitHub Actions now owns sanity, unit, documentation, package-build, and VM
integration checks. The integration matrix runs on `ubuntu-24.04` x86 runners
for all supported core branches and `devel`. Each job checks KVM and free disk
space, builds a controller image from the checkout, downloads the VS image
separately, and mounts it read-only. Public runners provide 4 CPUs and 16 GiB
RAM, enough for the 8 GiB VM; the separate image avoids a second large copy in a
Docker image layer. No self-hosted runner or Azure credentials are needed.

The stable `check` status requires both the sanity/unit and integration matrices.
VM console logs, container logs, and ansible-test output are retained as GitHub
artifacts for seven days, including after failure. Boot and download failures
fail the job; unavailable KVM does not silently skip integration.

The Azure pipeline source is retired. Historical Azure runs are retained for
reference. GitHub branch protection should require `check`, replacing the old
`ansible-collections.community.sonic` status supplied by Azure, after the new
GitHub integration jobs have been verified. Disabling the remote Azure pipeline
and cancelling its already queued jobs requires Azure administrator access;
removing a repository YAML file does not cancel already queued remote jobs.
