#!/usr/bin/env bash
# One-time environment setup for the ProPresenter Claude skill.
#
# - Creates a local virtualenv (.venv) so nothing pollutes system Python.
# - Installs the official `protobuf` + `grpcio-tools` packages (Google's
#   own packages, used here as a stand-in for `protoc` -- no third-party
#   code execution beyond that).
# - Fetches the community-maintained proto schema (submodule) from
#   https://github.com/greyshirtguy/ProPresenter7-Proto
# - Compiles Python bindings for every vendored ProPresenter schema
#   version into pygen/<version>/
#
# Safe to re-run; it's idempotent.

set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"

echo "==> Checking for python3..."
command -v python3 >/dev/null || { echo "python3 not found. Install Python 3.9+ first."; exit 1; }

echo "==> Creating virtualenv at .venv (if missing)..."
if [ ! -d ".venv" ]; then
  python3 -m venv .venv
fi
source .venv/bin/activate

echo "==> Installing protobuf + grpcio-tools into .venv..."
pip install --quiet --upgrade pip
pip install --quiet protobuf grpcio-tools

echo "==> Fetching the community ProPresenter proto schema submodule..."
if [ ! -d "proto/.git" ] && [ -f ".gitmodules" ]; then
  git submodule update --init --recursive
elif [ ! -d "proto" ]; then
  echo "    (not a git checkout with submodules configured -- cloning directly instead)"
  git clone --depth 1 https://github.com/greyshirtguy/ProPresenter7-Proto.git proto
else
  echo "    proto/ already present, skipping fetch"
fi

echo "==> Compiling Python bindings for each vendored schema version..."
mkdir -p pygen
for version_dir in "proto/Proto 7.16" "proto/Proto7.16.2" "proto/Proto 19beta"; do
  if [ ! -d "$version_dir" ]; then
    continue
  fi
  slug=$(basename "$version_dir" | tr ' ' '_')
  outdir="pygen/$slug"
  mkdir -p "$outdir"
  echo "    -> $version_dir  =>  $outdir"
  python3 -m grpc_tools.protoc -I "$version_dir" --python_out="$outdir" "$version_dir"/*.proto
done

echo ""
echo "==> Done. Compiled schema versions:"
ls pygen
echo ""
echo "To use a version in a script:"
echo '    import sys; sys.path.insert(0, "pygen/Proto7.16.2")'
echo '    import presentation_pb2, cue_pb2, uuid_pb2, propDocument_pb2'
echo ""
echo "Ask the user their ProPresenter version (Help -> About) and pick the"
echo "closest matching compiled schema. If unsure, try 19beta first for any"
echo "recent (2025+) install, since ProPresenter's versioning moved past 7.x."
