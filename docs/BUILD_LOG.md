# Swiss build log (private fork groundwork)

**Unofficial.** This is a private build environment for the "Pawtation theme, unofficial, based on Swiss" fork
described in `FORK_GUIDE.md` section 1. Swiss (github.com/emukidid/swiss-gc, GPL-2.0, by emu_kidid, Extrems and
contributors) is not affiliated with this project. Nothing from here goes upstream: no pull requests, issues,
discussions or support requests, and builds are not shared. Nothing has been pushed anywhere.

Recorded 2026-11-15. Everything lives outside this repo in `/home/user/swiss-work` (not committed).

## 1. What the environment is

| Item | Value |
|---|---|
| Source | `/home/user/swiss-work/swiss-gc`, tag `v0.6r2119`, commit `163f8b1de75328ad3a9a79caabff924930c04213` (2026-09-24, "Adjust for package change"), full history (2119 revisions), submodule `cube/swiss/source/littlefs` initialised. Unmodified. |
| Docker | Docker 29.9.2. `dockerd` runs with `--data-root /home/user/swiss-work/docker-data`; `build.sh` starts it if no daemon answers (root only). |
| Build image (default) | `swiss-build:local` (id `sha256:7b267ca8e36f...`) = `ghcr.io/extremscorner/libogc2@sha256:4de0a565af36168687aa8d36a9cd7ccb729cf41942bea5713eaefd3f5892be7a` (the image upstream CI uses, pinned by digest; created 2026-11-14) + the apt packages upstream CI installs: `7zip gcc gcc-mingw-w64-i686 libc6-dev libc6-i386 xorriso` (bookworm-backports). Recipe: `/home/user/swiss-work/docker/Dockerfile`. |
| Build image (release-era) | `swiss-build:20260924` (id `sha256:37fab390693b...`) = same Dockerfile on `ghcr.io/extremscorner/libogc2:20260924` = `@sha256:1cfc6190364c9272596b25f06fe22a9550914b1cf506ff701c3d421b78815f5c` (the toolchain snapshot from the tag's date). |
| Builds run | `docker run --rm --init --network none -v <checkout>:/src -w /src <image> make ...` |

### Tool versions (`build.sh --info`)

| | `swiss-build:local` (default) | `swiss-build:20260924` |
|---|---|---|
| powerpc-eabi-gcc | devkitPPC 16.2.0 | devkitPPC 16.1.0 |
| binutils (ld) | 2.47.20260726 | 2.46.0.20260210 |
| devkitPPC | r51-1 | r50-1 |
| devkitppc-newlib | 4.6.0.20260123-4 | 4.6.0.20260123-4 |
| libogc2-git | r2500.cb7745a-1 | r2468.34a540d-1 |
| libogc2-libdvm-git | r86.39a0c0b-1 | r85.420b9ae-2 |
| gamecube-tools-git | r99.9545458-1 | r99.9545458-1 |
| ppc-libiconv / ppc-libuchardet | 1.19-6 / 0.0.8-2 | 1.19-4 / 0.0.8-1 |
| 7-Zip / xorriso | 25.01 / 1.5.4 | 25.01 / 1.5.4 |

The official r2119 ELF's `.comment` says `GCC: (devkitPPC) 16.1.0`, matching the 20260924 image, not the default one.

## 2. How it was built (exact commands)

```sh
# image (needs network; behind a TLS-intercepting proxy build.sh passes the proxy env as build args
# and the CA bundle as a BuildKit secret, so the CA is never stored in the image)
/home/user/swiss-work/build.sh --image
# release-era image
SWISS_BASE_IMAGE=ghcr.io/extremscorner/libogc2:20260924 SWISS_IMAGE=swiss-build:20260924 \
  /home/user/swiss-work/build.sh --image
# full build (= upstream CI's plain `make`); build.sh removes an old swiss_rN/ first
SWISS_IMAGE=swiss-build:20260924 /home/user/swiss-work/build.sh      # what is in swiss-gc/swiss_r2119 now
/home/user/swiss-work/build.sh                                       # default image; copy kept in artifacts/v0.6r2119
# fast target, verified again on 2026-11-15 from a fresh shell (dockerd was started by the script)
/home/user/swiss-work/build.sh --info
/home/user/swiss-work/build.sh dev        # 1 min 30 s, exit 0, produces cube/swiss/swiss.dol + swiss.elf
```

The `dev` rebuild on 2026-11-15 produced `cube/swiss/swiss.dol` with sha256 `a140f6dd...b983`, identical to the
`swiss.dol` saved from the earlier full build with the same image (`artifacts/v0.6r2119/intermediate/`). So our own
build is repeatable on the same image.

## 3. Artifacts

### Full build, `swiss-build:20260924`, in `/home/user/swiss-work/swiss-gc/` (matches `logs/mine-20260924.sha`)

| File (under `swiss_r2119/` unless noted) | Bytes | sha256 |
|---|---|---|
| `ActionReplay/AUTOEXEC.DOL` | 1350152 | `85f76b0987d64ba6449b5e167b254de38435b7f19571266e5467d96ed596acda` |
| `ActionReplay/SDLOADER.BIN` | 1349856 | `5e2bf58677ecb72395a65dee8a0fe44858499acfd32fa2567455c4237f372dc5` |
| `Apploader/EXTRACT_TO_ROOT.zip` | 1350388 | `a62660f93c39ba0b5e5c3e704431e5b3b7ea679547d1280b417ccd1347e914b8` |
| `DOL/Legacy/swiss_r2119-lz-viper.dol` | 1932688 | `52a31c43da2214f7b5f09df3c55eb262c23860012d98e876d38a936ed899c597` |
| `DOL/Legacy/swiss_r2119-lz.dol` | 1928232 | `c200ca73a5b9e221e1f9a2d52cd6c855943482ce3131d4fb2649161447465b48` |
| `DOL/swiss_r2119.dol` | 1350152 | `85f76b0987d64ba6449b5e167b254de38435b7f19571266e5467d96ed596acda` |
| `DOL/swiss_r2119.elf` | 10118684 | `8b0e3bc39a0aec01d96a59bf72e3e0b667d25dc08911feb047adad6935122ca8` |
| `FlippyDrive/EXTRACT_TO_ROOT.zip` | 1350318 | `05b3328a810cb394fe856702462dbb97ad2bd110bb103553965ac6e96e3c5ba1` |
| `GCLoader/EXTRACT_TO_ROOT.zip` | 1747110 | `c5ee0d0981286327ad04714aeb7c86bec14f6fb4298a4ab8785bce2cfd53ed9e` |
| `ISO/swiss_r2119(ntsc-j).iso` | 1746944 | `4e08492bf048a9aa43970dcc9cad573f58856fb26a91f4e40e34d6d71b86f4cd` |
| `ISO/swiss_r2119(ntsc-u).iso` | 1746944 | `8ebf8e3183fa9aab0343288056e1dc1a1e29b526570429a8c75a5579ffe49130` |
| `ISO/swiss_r2119(pal).iso` | 1746944 | `630b087a5995ca1d19f51b1ea54c0882524a2ff969060cde3fb599b1fb9ad7dc` |
| `LICENSE.txt` | 18092 | `8177f97513213526df2cf6184d8ff986c675afb514d4e68a404010521b880643` |
| `Licenses/libdeflate.txt` | 1078 | `4ad69099cb4374836fd27583d9991e2838cd86b6e4666ab26b2d32582c91e73a` |
| `Licenses/libdvm.txt` | 2123 | `7da59a8c1cf34798793829576e33849a1dc640f8b093baa21ad80c92bef0289e` |
| `Licenses/libgloss.txt` | 24369 | `4ef33c7bdd57f5fa8fbe3bdc0200245ab91c564c2ef530d95bbe7fd4070757cd` |
| `Licenses/libiconv.txt` | 26419 | `20e50fe7aae3e56378ebf0417d9de904f55a0e61e4df315333e632a4d3555d95` |
| `Licenses/libmad.txt` | 17992 | `32b1062f7da84967e7019d01ab805935caa7ab7321a7ced0e30ebe75e5df1670` |
| `Licenses/libogc2.txt` | 966 | `8dbaef26ce4be15343c4d273d660909cb5389492179e8dc1d0ad525ea131cf6d` |
| `Licenses/libpsoarchive.txt` | 26530 | `dc626520dcd53a22f727af3ee42c770e56c97a64fe3adb063799d8ab032fe551` |
| `Licenses/littlefs.txt` | 1523 | `0cb4ff1daf5fdc1359c6a6ee3116092f08fc100c9d58b1b77ab17bfd801f856d` |
| `Licenses/newlib.txt` | 78388 | `f3afe48e4bc6ed8466a42e9dacb6be1d8f9cbf5aac15cb8e474a5ccde8b40ef6` |
| `Licenses/rtems.txt` | 1316 | `7bef6796095b536b72b835b1425105cff747122542d28849408b9f8f231cd90a` |
| `Licenses/uchardet.txt` | 70517 | `107a29ccdd2d778aa2df5462f85dddfa099059abd22e064e07ec2cc9bafc37cd` |
| `Licenses/xxhash.txt` | 1389 | `6ffedbc0f7878612d2b23589f1ff2ab15633e1df7963a5d9fc750ec5500c7e7a` |
| `Licenses/zlib-ng.txt` | 867 | `6c9f0d975b41afaa34d22f55bb8986ce69e5cb7ad327cb2b28820cd425edf5ee` |
| `MemoryCard/boot.gci` | 1351744 | `165b13473202750930fdc73f3f38188a9ffff3c320cba1285fdc807d84897ed1` |
| `MemoryCard/dol2gci/dol2gci` | 860624 | `5ce80376a5c67991222db1e641d21c6111674ad0be8a11f3d17e759579a4524d` |
| `MemoryCard/dol2gci/dol2gci.cpp` | 12057 | `68ad55e07eba08a2b218b97ad117a9bcf8974038d4eff41fe0f4946f9c1262fe` |
| `MemoryCard/dol2gci/dol2gci.exe` | 251392 | `ac72e96a6f9fbe3b08a2007558189e756d210a961d6b52ab31d4d9e2254f6b79` |
| `MemoryCard/xeno.gci` | 1351744 | `880bf1f969660fa26227934a96a07ac9fa0fb2f3951422ac2cb9e70ce820872a` |
| `PicoBoot/gekkoboot/EXTRACT_TO_ROOT.zip` | 2700682 | `73c9d8ee384699316783aa1a8b5a4aeb4947e424d83fad17e6c17e34acfb4117` |
| `PicoBoot/swiss_r2119.uf2` | 5400576 | `a3b7f6bde57a74b1c18bea98e09a2ebbc87c4ec2537b866c9d43154952ecf8e1` |
| `PicoLoader/gekkoboot/EXTRACT_TO_ROOT.zip` | 2700682 | `0f23ad0e5e124b3022350b8da56a74aafedb7d842417ca7f511ebddeea799100` |
| `PicoLoader/swiss_r2119.uf2` | 6987776 | `6c4beac897e71d8b834edb1e83a31f5f887cf4e0967688ba19aa931e4c6e711a` |
| `SWISS_FILE_DESCRIPTIONS.txt` | 2328 | `371c7b7118273d360d7402154b5148be903950f41f0ef16f580a811d13f3d966` |
| `USBGeckoRemoteServer/swissserver` | 18480 | `189c3d2bb725b0e840d7bec620c80c96c814bef06b17f28879c96c1c9e5145c0` |
| `USBGeckoRemoteServer/swissserver.exe` | 83470 | `c6fb811bf1b9e39a57f4dcb9c237a9e19a1c56dc73fca0c1ed4748a122b40c22` |
| `WODE/swiss_r2119(wode_extcfg).iso` | 1746944 | `fcc79b2ab66cba9e9c9d292f8e1d23db0ffdad62a6e045b1e917547bcb2fd12b` |
| `Wii/EXTRACT_TO_ROOT.zip` | 1825531 | `0798356bb99f80a9795a48473390b1c67b775ab5f481b30aedf5e402c99c68d7` |
| `WiikeyFusion/RecoveryISO/swiss_r2119_Recovery.iso` | 1746944 | `b1ed76304ca6906441af2c8fb7f9418ce5b2293ed9af660294a0c03781cf6fe1` |
| `WiikeyFusion/swiss_r2119.fzn` | 1900544 | `f5240ef1a0b81dbb3c90d704d6baf5f4e53124ef5fed69458e5af7c22f6eef86` |
| `WiikeyFusion/swiss_r2119.fzn.fw` | 12288 | `b3c9013edd237f2d2f25e27fce08e812e2edbe297e707c6fc672364199cda051` |
| `swiss_r2119-changelog.txt` | 622 | `5daca13065cad3a78d8f8fb2383faac1ef3608fcbc2ddd534bf59f944e9361f4` |
| `swiss_r2119.sha256` | 3070 | `d8a873eb8e990d400b39711e72350b514dc076a604d39b18cd67ba875cc030d8` |
| `../swiss_r2119.7z` | 8438759 | `e7f449e0bc3c92e80b31254cfae8691bd8ee926b2a73b03e4f84bd56f83144d8` |
| `../swiss_r2119.tar.xz` | 9834136 | `b8d44c7a58e3d0b56d2b75274c0c526ccfd88ab9fab1c63148d5bb8d84752ddf` |

### `dev` build, default image, 2026-11-15

| File | Bytes | sha256 |
|---|---|---|
| `swiss-gc/cube/swiss/swiss.dol` (unpacked) | 3913696 | `a140f6dd175c596fc27ac4e51114008cb1973ba1a41596f0b1d63a1ef6c7b983` |
| `swiss-gc/cube/swiss/swiss.elf` | 10435108 | `2a9247e6e20adaa2da50ebd84e51d7c6a5d4464a63dc52fc8a1531a4241dd8a2` |

The full build with the default image (GCC 16.2.0) is kept in `/home/user/swiss-work/artifacts/v0.6r2119/` with its
own `SHA256SUMS` (packed `DOL/swiss_r2119.dol` = `26811c49...43e6`). Release archives for comparison:
`/home/user/swiss-work/official/` (`swiss_r2119.7z` sha256 `b9cddb38...7d70`, extracted under `official/extracted/`).

## 4. Reproducibility note

**Our build of the unmodified tag is not byte-identical to the official release.** Of the 45 files in
`swiss_r2119/`, 20 match the official release (`LICENSE.txt`, all of `Licenses/`, `SWISS_FILE_DESCRIPTIONS.txt`,
the changelog, `MemoryCard/dol2gci/*` and `WiikeyFusion/swiss_r2119.fzn.fw`). The other 25 differ: every compiled
binary (`DOL/*.dol`, `DOL/swiss_r2119.elf`, `AUTOEXEC.DOL`, `SDLOADER.BIN`, `*.gci`, `*.uf2`, `*.fzn`,
`USBGeckoRemoteServer/swissserver{,.exe}`), every container made from them (`*.iso`, `EXTRACT_TO_ROOT.zip`) and
`swiss_r2119.sha256`. This holds for both images and for the C-locale variant (`logs/verify-20260924-collateC.sha`).

Most likely reasons, from comparing the official `DOL/swiss_r2119.elf` with ours (20260924 image):
1. **Build path.** The official ELF contains `/home/extrems/swiss-gc/...` paths (debug info and at least one
   `__FILE__` string in `.rodata`); ours contains `/src/...`. This changes `.debug_*` sizes and `.rodata` bytes.
2. **Toolchain/library snapshot.** The default image is GCC 16.2.0; the official build used 16.1.0. With the
   20260924 image (16.1.0) section sizes are almost the same, but `.text` is 16 bytes smaller (0x1712f0 vs
   0x171300), `.sdata` 24 bytes smaller and `.bss` 12 bytes smaller, so some code differs. Not determined whether
   that is the path or a libogc2/libdvm revision difference (the tag commit itself says "Adjust for package
   change", 3 minutes after the 20260924 image was published).
3. **Packaging.** Zips and ISOs embed the files above (and probably timestamps), so they differ whenever the DOL does.
   Locale/collation is ruled out as the only cause (C-locale rebuild still differs).

Not done: a rebuild at `/home/extrems/swiss-gc` (attempt failed, see section 7) and a function-by-function
disassembly diff. **Verified:** the build completes, outputs have the expected names and sizes in the same range
as the official ones, the version string/short hash `163f8b1d` is embedded, and our own build is repeatable on the
same image. **Not verified:** functional equivalence on hardware or in an emulator.

## 5. Using it

```sh
/home/user/swiss-work/build.sh --help        # usage
/home/user/swiss-work/build.sh --info        # tool versions
/home/user/swiss-work/build.sh dev           # cube/swiss/swiss.dol, ~1.5 min
/home/user/swiss-work/build.sh               # full release set swiss_r2119/ (= upstream CI's `make`)
SWISS_IMAGE=swiss-build:20260924 /home/user/swiss-work/build.sh      # release-era toolchain
SWISS_SRC=/path/to/fork-checkout /home/user/swiss-work/build.sh dev  # build another checkout/worktree
/home/user/swiss-work/build.sh --shell       # shell in the container, cwd /src
source /home/user/swiss-work/env.sh; swiss_make dev                  # same via functions
```
Notes: every top-level target starts with `clean`; the output folder name is `swiss_r<N>` with N = commit count,
so a fork branch with extra commits becomes r2120, r2121, ...

`/home/user/swiss-work/shot.sh <file.dol> <out.png> [seconds]`: **not available** (section 6). By default it
prints that and exits 3. `SHOT_FORCE=1` runs the attempt anyway (image `swiss-dolphin:sid`, log in
`logs/dolphin/`); `SHOT_EMU_PATCH=1` additionally boots an emulator-only copy patched by
`docker-dolphin/emu-patch.pl`.

## 6. Emulator screenshot helper: not working

Setup: `docker-dolphin/Dockerfile` (Debian `dolphin-emu` + Xvfb + Mesa llvmpipe + ImageMagick),
`docker-dolphin/shot-inner.sh` (Xvfb, Dolphin `-p x11`, logging and PNG frame dumping on, falls back to grabbing
the X root window). Images: `swiss-dolphin:local` (bookworm, Dolphin 5.0-17995), `swiss-dolphin:trixie`
(Dolphin 2503), `swiss-dolphin:sid` (Dolphin 2609, built from a trixie base with `--build-arg SUITE=sid`).

Result: no `shots/baseline.png` was produced, because there is nothing truthful to put in it. Every attempt shows a
uniformly black 640x528 frame (`shots/diag-*.png`; mean brightness 0), Dolphin never presents a frame (frame dump
folder stays empty), and no VI/OSReport activity is logged. Tried: our unpacked `swiss.dol` and the
emulator-patched copy on all three Dolphin versions (JIT); the patched copy also with the interpreter core on 2503;
the official release `DOL/swiss_r2119.dol` on 2503. All black.
Observed in the logs:
- Unpatched: endless `Trying to read 32 bits from an invalid MMIO (addr=0c00688c)`. libogc2's `EXI_ImmEx`/`EXI_Sync`
  poll the EXI control register at `0xCC00688C` (0x80 above the canonical `0xCC00680C`), which Dolphin does not map.
- With `emu-patch.pl` (rewrites 2 polling sites to `0x680C`, emulator copy only): those reads stop, there is one
  read of unmapped `0xCC004028` in `__SYS_PreInit`, and then still nothing is drawn.
Conclusion: this libogc2/Swiss build does not run far enough in these Dolphin builds to show its UI. Where it stops
was not found (time-boxed). A newer Dolphin development build might work; untested.

## 7. What failed along the way and why

- Dolphin killed by `SIGBUS` on start: Docker's default 64 MB `/dev/shm` is too small for Dolphin's emulated RAM
  mapping. Fixed with `--shm-size=1g` (in `shot.sh`).
- Dolphin black screen: see section 6. Unresolved.
- `docker pull debian:sid-slim`: Docker Hub `429 Too Many Requests`. Worked around by building on the cached
  `debian:trixie-slim` and switching apt to sid (`SUITE=sid` build arg).
- Rebuild at the official path (`logs/build-all-verify-notag-tc20260924-collateC-path.log`): failed with
  `No rule to make target '/src/wii/booter/source/main.c'` because stale dependency files from the `/src` build
  pointed at the old path. Would need a fresh checkout mounted at `/home/extrems/swiss-gc`; not retried.
- `make[1]: powerpc-eabi-pkg-config: No such file or directory` appears at the start of `cube/swiss`; the build
  continues and succeeds (the image has `libogc2-pkg-config`). Same in every build; effect not investigated.
- The default image is what `ghcr.io/extremscorner/libogc2:latest` was on 2026-11-15 (now pinned by digest); it
  had moved to GCC 16.2.0 since the tag, hence the separate `swiss-build:20260924` image.

## 8. Recreate from scratch

### A. Linux machine behind a TLS-intercepting HTTPS proxy (as here)
```sh
mkdir -p ~/swiss-work && cd ~/swiss-work
# copy build.sh, env.sh, shot.sh, docker/ and docker-dolphin/ from /home/user/swiss-work
git clone https://github.com/emukidid/swiss-gc.git    # full clone, not --depth
git -C swiss-gc checkout v0.6r2119
git -C swiss-gc submodule update --init --recursive
export HTTPS_PROXY=... https_proxy=...                  # usually already set
SWISS_CA_BUNDLE=/path/to/proxy-ca.crt ./build.sh --image   # passes proxy args + CA as a build secret
./build.sh --info && ./build.sh dev && ./build.sh
```
git needs the proxy CA too (`git config --global http.sslCAInfo /path/to/proxy-ca.crt`); never disable TLS
verification. Builds themselves run with `--network none`. Release-era toolchain: add
`SWISS_BASE_IMAGE=ghcr.io/extremscorner/libogc2:20260924 SWISS_IMAGE=swiss-build:20260924` to the `--image` and
build commands.

### B. Normal PC with Docker Desktop (Windows/macOS)
```sh
git clone https://github.com/emukidid/swiss-gc.git
cd swiss-gc && git checkout v0.6r2119 && git submodule update --init --recursive && cd ..
docker build -t swiss-build:local path/to/swiss-work/docker          # no proxy args needed
docker run --rm --network none -v "$PWD/swiss-gc:/src" -w /src swiss-build:local make dev
docker run --rm --network none -v "$PWD/swiss-gc:/src" -w /src swiss-build:local make
```
On Windows run this from a WSL2 shell with the checkout inside the WSL filesystem (faster, and avoids CRLF
conversion: clone with `git config --global core.autocrlf false`). On Apple Silicon the image is amd64-only as far
as checked here; add `--platform linux/amd64` (emulated, slower; untested). `build.sh` itself also works on Linux
or WSL2 when Docker is already running.

## 9. Unverified

- **Nothing has run on real hardware.** No DOL from these builds has booted on a GameCube.
- No DOL from these builds (or the official one) has been seen running in an emulator.
- Bit-identity with the official release: not achieved; cause only partly explained (section 4).
- Docker Desktop and Apple Silicon instructions: written from the Linux setup, not tested.
