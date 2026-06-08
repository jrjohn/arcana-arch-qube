#!/usr/bin/env bash
#
# build-and-push.sh — build the arch-qube image as a SINGLE manifest and push.
#
# WHY --provenance=false / --sbom=false (do NOT remove):
#   buildx defaults to emitting an OCI image INDEX with an attestation child
#   manifest. The private registry's nightly GC (docker-cleanup.sh:
#   `registry garbage-collect --delete-untagged`) then deletes that child —
#   it has no tag of its own, only an index reference — leaving `latest` a
#   dangling index that points at a 404. Every pull then fails with
#   "manifest <sha> not found" (2026-06-07: this silently broke arch-qube on
#   ALL pipelines a day after a rebuild). A single image manifest has no
#   untagged child, so GC can't strip it. arch-qube is a single-arch tool —
#   it never needs a multi-arch index.
#
# Usage (run on the build host that talks to the target registry, e.g. bluesea):
#   ./build-and-push.sh                       # arcana.boo/arcana/arch-qube:latest, linux/arm64
#   PLATFORM=linux/amd64 ./build-and-push.sh   # override arch
#   IMAGE=other/ref:tag ./build-and-push.sh    # override target
set -euo pipefail
IMAGE="${IMAGE:-arcana.boo/arcana/arch-qube:latest}"
PLATFORM="${PLATFORM:-linux/arm64}"

cd "$(dirname "$0")"
echo "building $IMAGE ($PLATFORM) as single manifest (no provenance/attestation)"
docker buildx build \
  --provenance=false \
  --sbom=false \
  --platform "$PLATFORM" \
  -t "$IMAGE" \
  --push .

# verify the pushed tag is a single image manifest, not an index — fail loudly
# if buildx regressed to an index (the exact failure mode this script prevents)
repo_path="${IMAGE#*/}"; repo="${repo_path%:*}"; tag="${IMAGE##*:}"
reg_host="${IMAGE%%/*}"
mt=$(curl -fsS \
  -H "Accept: application/vnd.docker.distribution.manifest.v2+json" \
  -H "Accept: application/vnd.oci.image.manifest.v1+json" \
  "http://localhost:5000/v2/${repo}/manifests/${tag}" 2>/dev/null \
  | python3 -c "import sys,json;print(json.load(sys.stdin).get('mediaType',''))" 2>/dev/null || echo "")
case "$mt" in
  *manifest.v2+json|*image.manifest.v1+json)
    echo "OK: $IMAGE is a single manifest ($mt)" ;;
  *index*|*manifest.list*)
    echo "FAIL: $IMAGE is an INDEX ($mt) — GC will strip its child. Aborting." >&2
    exit 1 ;;
  *)
    echo "WARN: could not verify manifest type via localhost:5000 (registry not local?)" ;;
esac
