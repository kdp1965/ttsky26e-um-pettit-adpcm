#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
# publish.sh [PLAYER_DIR] - copy this folder to a checkout of
# kdp1965/uadpcm-player (default ../../uadpcm-player), whose main branch is
# the GitHub Pages site https://kdp1965.github.io/uadpcm-player/, and commit
# it there.  It does not push: look at the commit, then `git push` in that
# checkout.  (A push with several new songs can time out: push them a commit
# at a time.)
set -e
here=$(cd "$(dirname "$0")" && pwd)
dest=${1:-$here/../../uadpcm-player}
[ -d "$dest/.git" ] || { echo "no checkout at $dest: git clone https://github.com/kdp1965/uadpcm-player.git" >&2; exit 1; }
python3 "$here/mksongs.py" > "$here/songs/songs.js"
rsync -a --delete --exclude .git --exclude .gitignore --exclude .nojekyll --exclude LICENSE --exclude README.md \
      --exclude publish.sh --exclude '*.swp' "$here/" "$dest/"
cd "$dest"
git add -A
if git diff --cached --quiet; then echo "nothing to publish"; exit 0; fi
git commit -q -m "Update from ttsky26e-um-pettit-adpcm $(git -C "$here" rev-parse --short HEAD)"
git --no-pager log --stat -1 | tail -n +5
echo "committed in $dest; push it with: git -C $dest push"
