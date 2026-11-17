#!/usr/bin/env bash
# Builds the deliverables: report + slides (PDF) and the Moodle archive.
# Screenshots are made separately with scripts/capture.py (needs Playwright + Chromium).
set -euo pipefail
cd "$(dirname "$0")"
ROOT=../..
mkdir -p build

for doc in rapport presentation; do
  for _ in 1 2; do xelatex -interaction=nonstopmode -halt-on-error "$doc.tex" > "build/$doc.log"; done
  echo "built $doc.pdf"
done

# Moodle archive: PDFs + full source code + sample database (no TLS key, no password file)
NAME=Robison_Marc_5A_ESE_projet_integre
rm -rf "build/$NAME" "$NAME.zip"
mkdir -p "build/$NAME/code"
cp rapport.pdf presentation.pdf "build/$NAME/"
git -C "$ROOT" archive HEAD -- main.py Makefile requirements.txt README.md .gitignore \
    security_station tests docs/figures | tar -x -C "build/$NAME/code"
mkdir -p "build/$NAME/code/base_de_donnees"
cp donnees/security.db donnees/security_logs.csv "build/$NAME/code/base_de_donnees/"
(cd build && zip -qr "../$NAME.zip" "$NAME")
echo "built $NAME.zip"
