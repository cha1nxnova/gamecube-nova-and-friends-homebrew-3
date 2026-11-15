# mods/

One folder per game, named with the game's catalog key (see `python -m pawtation scan`, or start one with
`python -m pawtation mods --new "paper mario"`).

    mods/<game-key>/card/...      everything here is copied to the SAME path on the SD card whenever that
                                  game rotates onto a card, and removed when it rotates off
    mods/<game-key>/README.md     your notes (never copied)

Example: `mods/paper-mario-ttyd/card/swiss/cheats/G8ME01.txt` lands at `<card>/swiss/cheats/G8ME01.txt`,
which is where Swiss looks for a game's cheat codes. Full guide: `docs/MODDING.md`.
