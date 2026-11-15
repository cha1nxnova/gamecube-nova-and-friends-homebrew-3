# Swiss (swiss-gc) build environment - UNOFFICIAL, private/personal use only.
#
# Base: the same container image upstream CI uses (devkitPPC + libogc2 + ppc portlibs),
# pinned by digest so the toolchain cannot change underneath you.
# Added: exactly the host packages upstream CI installs before running `make`
# (.github/workflows/continuous-integration-workflow.yml at tag v0.6r2119).
#
# Build (normal PC):   docker build -t swiss-build:local /path/to/this/dir
# Build (behind a TLS-intercepting HTTPS proxy, as build.sh does automatically):
#   docker build --network host \
#     --build-arg https_proxy=$https_proxy --build-arg HTTPS_PROXY=$HTTPS_PROXY \
#     --secret id=proxyca,src=/path/to/ca-bundle.crt -t swiss-build:local .
ARG BASE=ghcr.io/extremscorner/libogc2@sha256:4de0a565af36168687aa8d36a9cd7ccb729cf41942bea5713eaefd3f5892be7a
FROM ${BASE}

# If a proxy CA bundle is supplied as a build secret, talk to the Debian mirror over HTTPS
# and verify against that bundle (the bundle itself is NOT stored in the image).
# Without the secret, the image's stock (plain http) apt sources are used unchanged.
RUN --mount=type=secret,id=proxyca,required=false,mode=0444 \
    set -eu; \
    opts=""; \
    if [ -s /run/secrets/proxyca ]; then \
        find /etc/apt -type f \( -name '*.list' -o -name '*.sources' \) -exec \
            sed -i 's|http://deb.debian.org|https://deb.debian.org|g' {} +; \
        opts="-o Acquire::https::CAInfo=/run/secrets/proxyca"; \
    fi; \
    apt-get $opts update; \
    apt-get $opts install -y --no-install-recommends -t bookworm-backports \
        7zip gcc gcc-mingw-w64-i686 libc6-dev libc6-i386 xorriso; \
    if [ -s /run/secrets/proxyca ]; then \
        find /etc/apt -type f \( -name '*.list' -o -name '*.sources' \) -exec \
            sed -i 's|https://deb.debian.org|http://deb.debian.org|g' {} +; \
    fi; \
    rm -rf /var/lib/apt/lists/*

# The source tree is bind-mounted and may be owned by a different uid than the one
# running make; the top-level Makefile calls git (revision number, short hash).
RUN git config --system --add safe.directory '*'

# Convenience only: lets `build.sh --exec powerpc-eabi-objdump ...` work. Appended at the END of
# PATH so nothing the stock image resolves is shadowed (the Makefiles call $(DEVKITPPC)/bin/... anyway).
ENV PATH="${PATH}:/opt/devkitpro/devkitPPC/bin"

LABEL org.opencontainers.image.title="swiss-build (unofficial)" \
      org.opencontainers.image.description="Unofficial local build environment for Swiss; not affiliated with or supported by the Swiss project."

WORKDIR /src
