#!/usr/bin/env python3
"""Pack the rendered STLs into 3MF plates for Bambu Studio (or any slicer).

Each part becomes its own named object, already in print orientation and placed on a
256 x 256 mm plate (Bambu A1, P1, X1). Run build.sh instead of calling this directly.

    python3 make_3mf.py
"""
import os
import re
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
STL = os.path.join(HERE, "stl")

# (output file, [(object name, stl file, [(x, y) centre on the plate, one per copy])])
PLATES = [
    ("head_mount_plate.3mf", [
        ("head", "head.stl", [(128, 170)]),
        ("foot_left", "foot_left.stl", [(40, 70)]),
        ("foot_right", "foot_right.stl", [(70, 70)]),
        ("slider", "slider.stl", [(115, 70), (160, 70)]),
    ]),
    ("test_plate.3mf", [
        ("test_galvo", "test_galvo.stl", [(128, 128)]),
    ]),
]


def read_stl(path):
    """ASCII STL -> (vertices, triangles) with shared vertices."""
    text = open(path).read()
    coords = re.findall(r"vertex\s+(\S+)\s+(\S+)\s+(\S+)", text)
    index, verts, tris = {}, [], []
    for i in range(0, len(coords), 3):
        tri = []
        for c in coords[i:i + 3]:
            p = tuple(round(float(v), 5) for v in c)
            if p not in index:
                index[p] = len(verts)
                verts.append(p)
            tri.append(index[p])
        if len(set(tri)) == 3:
            tris.append(tri)
    return verts, tris


def centred(verts):
    """Move the mesh so its footprint is centred on x = y = 0 and it sits on z = 0."""
    lo = [min(v[k] for v in verts) for k in range(3)]
    hi = [max(v[k] for v in verts) for k in range(3)]
    off = [(lo[0] + hi[0]) / 2, (lo[1] + hi[1]) / 2, lo[2]]
    return [(v[0] - off[0], v[1] - off[1], v[2] - off[2]) for v in verts], [h - l for l, h in zip(lo, hi)]


def model_xml(parts):
    objs, items = [], []
    for oid, (name, stl, places) in enumerate(parts, start=1):
        verts, tris = read_stl(os.path.join(STL, stl))
        verts, size = centred(verts)
        v = "".join(f'<vertex x="{x:.5f}" y="{y:.5f}" z="{z:.5f}"/>' for x, y, z in verts)
        t = "".join(f'<triangle v1="{a}" v2="{b}" v3="{c}"/>' for a, b, c in tris)
        objs.append(f'<object id="{oid}" name="{name}" type="model"><mesh><vertices>{v}</vertices>'
                    f'<triangles>{t}</triangles></mesh></object>')
        for x, y in places:
            items.append(f'<item objectid="{oid}" transform="1 0 0 0 1 0 0 0 1 {x} {y} 0"/>')
        print(f"  {name:12s} x{len(places)}  {size[0]:.1f} x {size[1]:.1f} x {size[2]:.1f} mm")
    return ('<?xml version="1.0" encoding="UTF-8"?>\n'
            '<model unit="millimeter" xml:lang="en-US" '
            'xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02">'
            '<metadata name="Title">LLTS head mount</metadata>'
            f'<resources>{"".join(objs)}</resources><build>{"".join(items)}</build></model>')


CONTENT_TYPES = ('<?xml version="1.0" encoding="UTF-8"?>\n'
                 '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                 '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
                 '<Default Extension="model" ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/>'
                 '</Types>')
RELS = ('<?xml version="1.0" encoding="UTF-8"?>\n'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Target="/3D/3dmodel.model" Id="rel0" '
        'Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/></Relationships>')

if __name__ == "__main__":
    for out, parts in PLATES:
        print(out)
        with zipfile.ZipFile(os.path.join(HERE, out), "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("[Content_Types].xml", CONTENT_TYPES)
            z.writestr("_rels/.rels", RELS)
            z.writestr("3D/3dmodel.model", model_xml(parts))
