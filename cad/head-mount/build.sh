#!/usr/bin/env bash
# Render every printable part to STL and pack them into 3MF plates for Bambu Studio.
# Needs OpenSCAD (brew install --cask openscad@snapshot) and python3.
set -euo pipefail
cd "$(dirname "$0")"
mkdir -p stl
for p in head slider foot_left foot_right test_camera test_galvo test_socket; do
    echo "rendering $p"
    openscad --backend=manifold -D "part=\"$p\"" -o "stl/$p.stl" llts_head.scad 2>&1 | grep -E "ECHO|WARNING|ERROR" | sed 's/^/  /' || true
done
python3 make_3mf.py
