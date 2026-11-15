#!/usr/bin/env bash
# apply.sh - rebuild the private, unofficial "Pawtation" theme of Swiss from the pinned tag plus
# the patch queue in patches/. Not affiliated with or supported by the Swiss project.
# This script never pushes, never adds remotes and never contacts anyone but GitHub (for the clone).
#
# USAGE
#   swiss_fork/apply.sh                 # clone (or reuse SWISS_SRC), verify, git am, full build (make)
#   swiss_fork/apply.sh dev             # same, but `make dev` (unpacked cube/swiss/swiss.dol only)
#   swiss_fork/apply.sh --no-build      # stop after the patches are applied and verified
#
# ENVIRONMENT
#   SWISS_SRC     checkout to use (default: ./swiss-gc-pawtation). Cloned with full history if
#                 missing. If it exists it must be a clean clone that has the tag, and must not
#                 already have a 'pawtation-theme' branch.
#   SWISS_IMAGE   Docker image with the toolchain (default swiss-build:local; built from
#                 swiss_fork/docker/Dockerfile if missing).
#
# Refuses to continue (exit 1) on ANY mismatch: tag commit, patch checksums, patch application,
# resulting source tree.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
UPSTREAM_URL="https://github.com/emukidid/swiss-gc.git"
TAG="v0.6r2119"
TAG_COMMIT="163f8b1de75328ad3a9a79caabff924930c04213"
RESULT_TREE="f8721a7a523aaad5846585209ed02eb8a660c0f7"   # tree of tag + all patches
BRANCH="pawtation-theme"
SWISS_SRC="${SWISS_SRC:-$PWD/swiss-gc-pawtation}"
SWISS_IMAGE="${SWISS_IMAGE:-swiss-build:local}"

die() { printf 'apply.sh: %s\n' "$*" >&2; exit 1; }
msg() { printf '[apply] %s\n' "$*" >&2; }

target="all"; build=1
case "${1:-}" in
    "") ;;
    dev) target="dev" ;;
    --no-build) build=0 ;;
    -h|--help) sed -n '2,/^set -euo/p' "${BASH_SOURCE[0]}" | sed -e '$d' -e 's/^# \{0,1\}//'; exit 0 ;;
    *) die "unknown argument: $1 (see --help)" ;;
esac

# 1. patch queue integrity
( cd "$HERE/patches" && sha256sum --quiet -c SHA256SUMS ) || die "patches/ do not match patches/SHA256SUMS"
shopt -s nullglob; patches=("$HERE"/patches/*.patch); shopt -u nullglob
[ ${#patches[@]} -gt 0 ] || die "no patches in $HERE/patches"

# 2. source checkout
if [ ! -e "$SWISS_SRC" ]; then
    msg "cloning $UPSTREAM_URL (full history) into $SWISS_SRC"
    git clone "$UPSTREAM_URL" "$SWISS_SRC"
fi
git -C "$SWISS_SRC" rev-parse --git-dir >/dev/null 2>&1 || die "$SWISS_SRC is not a git checkout"
[ "$(git -C "$SWISS_SRC" rev-parse --is-shallow-repository)" = false ] || die "$SWISS_SRC is shallow; the revision number needs full history"
got="$(git -C "$SWISS_SRC" rev-parse -q --verify "$TAG^{commit}" 2>/dev/null)" || die "tag $TAG not found in $SWISS_SRC"
[ "$got" = "$TAG_COMMIT" ] || die "tag $TAG is $got, expected $TAG_COMMIT"
[ -z "$(git -C "$SWISS_SRC" status --porcelain --untracked-files=no)" ] || die "$SWISS_SRC has local changes; use a clean checkout"
git -C "$SWISS_SRC" rev-parse -q --verify "refs/heads/$BRANCH" >/dev/null && die "branch $BRANCH already exists in $SWISS_SRC; use a fresh checkout"

# 3. branch + patches (local only)
git -C "$SWISS_SRC" checkout -q -b "$BRANCH" "$TAG"
git -C "$SWISS_SRC" submodule update --init --recursive
git -C "$SWISS_SRC" config user.name "Pawtation fork"
git -C "$SWISS_SRC" config user.email "fork@localhost"
if git -C "$SWISS_SRC" remote get-url origin >/dev/null 2>&1; then
    git -C "$SWISS_SRC" config remote.origin.pushurl "DISABLED-never-push"
fi
if ! git -C "$SWISS_SRC" am -q --keep-cr --whitespace=nowarn "${patches[@]}"; then
    git -C "$SWISS_SRC" am --abort || true
    die "git am failed; nothing applied"
fi
tree="$(git -C "$SWISS_SRC" rev-parse "HEAD^{tree}")"
[ "$tree" = "$RESULT_TREE" ] || die "patched tree is $tree, expected $RESULT_TREE"
msg "patched and verified: $(git -C "$SWISS_SRC" rev-list --count "$TAG..HEAD") commits on $BRANCH, tree $tree"
[ $build = 1 ] || exit 0

# 4. build in Docker (no network during the build)
command -v docker >/dev/null || die "docker not found"
if ! docker image inspect "$SWISS_IMAGE" >/dev/null 2>&1; then
    msg "building image $SWISS_IMAGE from $HERE/docker/Dockerfile"
    docker build -t "$SWISS_IMAGE" "$HERE/docker"
fi
rev="$(git -C "$SWISS_SRC" rev-list HEAD | wc -l | tr -d ' ')"
if [ "$target" = all ]; then rm -rf "$SWISS_SRC/swiss_r$rev"; fi
docker run --rm --init --network none -v "$(cd "$SWISS_SRC" && pwd):/src" -w /src "$SWISS_IMAGE" make "$target"
if [ "$target" = all ]; then
    msg "done: $SWISS_SRC/swiss_r$rev/DOL/swiss_r$rev.dol and ActionReplay/AUTOEXEC.DOL"
    ( cd "$SWISS_SRC/swiss_r$rev" && sha256sum "DOL/swiss_r$rev.dol" ActionReplay/AUTOEXEC.DOL )
else
    msg "done: $SWISS_SRC/cube/swiss/swiss.dol"
fi
