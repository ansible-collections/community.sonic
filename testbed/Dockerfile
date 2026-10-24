FROM debian:trixie

ARG ANSIBLE_CORE_REF=stable-2.21

RUN apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install --no-install-recommends -y \
      wget ca-certificates curl jq

ARG SONIC_BRANCH=202605
ARG SONIC_IMAGE_URL=
ARG DOWNLOAD_SONIC_IMAGE=true
COPY download-image.sh /usr/local/bin/download-sonic-image
RUN if [ "$DOWNLOAD_SONIC_IMAGE" = true ]; then /usr/local/bin/download-sonic-image; fi

RUN apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install --no-install-recommends -y \
      ca-certificates moreutils \
      python3-venv python3-setuptools jq curl qemu-system-x86 sshpass ssh \
      tini git rsync locales

RUN sed -i '/en_US.UTF-8/s/^# //g' /etc/locale.gen && locale-gen
ENV LANG=en_US.UTF-8
ENV LC_ALL=en_US.UTF-8

RUN useradd -m ubuntu

COPY requirements.txt /tmp/
COPY galaxy-requirements.yml /tmp/

RUN python3 -m venv /usr/local/ansible-venv && \
      /usr/local/ansible-venv/bin/pip3 install -r /tmp/requirements.txt \
        "ansible-core @ git+https://github.com/ansible/ansible.git@${ANSIBLE_CORE_REF}" && \
      /usr/local/ansible-venv/bin/ansible-galaxy collection install -r /tmp/galaxy-requirements.yml && \
      /usr/local/ansible-venv/bin/ansible-galaxy role install -r /tmp/galaxy-requirements.yml && \
      rm -f /tmp/requirements.txt /tmp/galaxy-requirements.yml && \
      chown -R ubuntu: /usr/local/ansible-venv

ENV PATH=/usr/local/ansible-venv/bin:$PATH

COPY ssh_config /etc/ssh/ssh_config.d/sonic-vs.conf

COPY docker.sh /
ENTRYPOINT ["/usr/bin/tini"]
