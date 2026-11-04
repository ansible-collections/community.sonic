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

# Download the compressed image to a temporary file first so a connection
# reset mid-transfer (the artifact server does that now and then) is retried
# and resumed instead of failing the job, then decompress. Publish the image
# only after both steps succeed, preserving any existing cached image if a
# transfer stalls or an archive is truncated.
target=${SONIC_IMAGE_PATH:-/opt/sonic-vs.img}
partial=$(mktemp "${target}.XXXXXX")
archive="${partial}.gz"
trap 'rm -f -- "$partial" "$archive"' EXIT
attempt=0
until curl -fL --connect-timeout 30 --speed-time 60 --speed-limit 1024 \
    --max-time 1200 --retry 5 --retry-delay 10 --retry-all-errors \
    -C - -o "$archive" "$SONIC_IMAGE_URL"; do
  attempt=$((attempt + 1))
  if (( attempt >= 3 )); then
    echo "Giving up downloading $SONIC_IMAGE_URL after $attempt attempts" >&2
    exit 1
  fi
  echo "Download interrupted, resuming (attempt $((attempt + 1)))" >&2
  sleep 15
done
gzip -t "$archive"
gzip -dc "$archive" | dd of="$partial" bs=1M conv=sparse status=none
rm -f -- "$archive"
mv "$partial" "$target"
