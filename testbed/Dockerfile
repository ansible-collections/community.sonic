FROM debian:bullseye

RUN apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install --no-install-recommends -y \
      wget ca-certificates curl jq

RUN \
  branch=202211; \
  pipeid="$(curl -s 'https://dev.azure.com/mssonic/build/_apis/build/definitions?name=Azure.sonic-buildimage.official.vs'  | jq -r '.value[0].id')"; \
  bldid="$(curl -s 'https://dev.azure.com/mssonic/build/_apis/build/builds?definitions='"${pipeid}"'&branchName=refs/heads/'"${branch}"'&$top=1&resultFilter=succeeded&api-version=6.0' | jq -r '.value[0].id')"; \
  url="$(curl -s 'https://dev.azure.com/mssonic/build/_apis/build/builds/'"${bldid}"'/artifacts?artifactName=sonic-buildimage.vs&api-version=5.1' | jq -r '.resource.downloadUrl')"; \
  echo "${url}"; \
  wget --progress=dot:giga $(echo "${url}" | sed 's/format=zip/format=file\&subpath=\/target\/sonic-vs.img.gz/') \
    -O sonic-vs.img.gz 2>&1 && gunzip sonic-vs.img.gz && mv /sonic-vs.img /opt/

RUN apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install --no-install-recommends -y \
      meson g++ libyaml-cpp-dev pkg-config ca-certificates moreutils \
      python3-venv python3-setuptools jq curl qemu-system-x86 sshpass socat ssh \
      tini git rsync locales

RUN sed -i '/en_US.UTF-8/s/^# //g' /etc/locale.gen && locale-gen
ENV LANG en_US.UTF-8
ENV LC_ALL en_US.UTF-8

RUN wget 'https://github.com/nixcloud/ip2unix/archive/refs/tags/v2.1.4.tar.gz' -O ip2unix.tar.gz && \
  tar -xvf ip2unix.tar.gz && rm -f ip2unix.tar.gz
RUN cd ip2unix-*/ && meson build && ninja -C build && ninja -C build install && ldconfig

RUN useradd -m ubuntu

COPY requirements.txt /tmp/
COPY galaxy-requirements.yml /tmp/

RUN python3 -m venv /usr/local/ansible-venv && \
      /usr/local/ansible-venv/bin/pip3 install -r /tmp/requirements.txt && \
      /usr/local/ansible-venv/bin/ansible-galaxy collection install -r /tmp/galaxy-requirements.yml && \
      /usr/local/ansible-venv/bin/ansible-galaxy role install -r /tmp/galaxy-requirements.yml && \
      rm -f /tmp/requirements.txt /tmp/galaxy-requirements.yml && \
      chown -R ubuntu: /usr/local/ansible-venv

ENV PATH /usr/local/ansible-venv/bin:$PATH

COPY ssh_config /home/ubuntu/.ssh/config
RUN chown -R ubuntu.ubuntu /home/ubuntu/.ssh

COPY docker.sh /
ENTRYPOINT ["/usr/bin/tini"]
