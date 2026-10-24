#!/usr/bin/env bash
set -euo pipefail

# A supplied URL allows a retained/pinned image to be used after Azure expires
# its artifacts. Otherwise discover the latest successful VS build on a branch.
if [[ -z "${SONIC_IMAGE_URL:-}" ]]; then
  api=https://dev.azure.com/mssonic/build/_apis/build
  definition=$(curl -fsSL "$api/definitions?name=Azure.sonic-buildimage.official.vs&api-version=7.1" |
    jq -er '.value[0].id')
  build=$(curl -fsSL --get "$api/builds" \
    --data-urlencode "definitions=$definition" \
    --data-urlencode "branchName=refs/heads/${SONIC_BRANCH:-202605}" \
    --data-urlencode "\$top=1" \
    --data-urlencode 'resultFilter=succeeded' \
    --data-urlencode 'api-version=7.1' | jq -er '.value[0].id')
  url=$(curl -fsSL "$api/builds/$build/artifacts?artifactName=sonic-buildimage.vs&api-version=7.1" |
    jq -er '.resource.downloadUrl')
  url=${url/format=zip/format=file}
  SONIC_IMAGE_URL="${url}&subPath=%2Ftarget%2Fsonic-vs.img.gz"
fi

# Publish the image only after curl and gzip both succeed, preserving any
# existing cached image if a transfer stalls or an archive is truncated.
target=${SONIC_IMAGE_PATH:-/opt/sonic-vs.img}
partial=$(mktemp "${target}.XXXXXX")
trap 'test ! -e "$partial" || rm -- "$partial"' EXIT
curl -fL --connect-timeout 30 --speed-time 60 --speed-limit 1024 \
  --max-time 1200 "$SONIC_IMAGE_URL" | gzip -dc | \
  dd of="$partial" bs=1M conv=sparse status=none
mv "$partial" "$target"
