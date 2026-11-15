# T5: Swiss build baseline (PATH B ONLY - requires the user's written approval recorded in HANDOFF.md)
Read docs/FORK_GUIDE.md fully first, especially section 1 (maintainer's no-LLM-contributions policy). Do NOT send anything upstream.
Goal: reproducible build of an UNMODIFIED Swiss release tag outside this repo and a written build log (toolchain versions, commands, hashes).
Stop and report if: no network, no devkitPPC/libogc2/container, or the user has not approved Path B. Do not substitute guesses for missing steps.
No hardware testing without the user present; follow section 5's protocol. Edit only docs/ and a new `docs/BUILD_LOG.md`.
