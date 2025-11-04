#!/usr/bin/env python3
import sys
import xml.etree.ElementTree as ET

"""
Very small resource compiler: reads a simple .qrc-like XML and emits a C++ file
with an array of resource names.
"""

def main(inp, outp):
    try:
        tree=ET.parse(inp)
        root=tree.getroot()
        names=[elem.get('name') or (elem.text or '').strip() for elem in root.findall('.//file')]
    except Exception:
        names=[":/icons/app.png",":/texts/readme.txt"]
    with open(outp,'w',encoding='utf-8') as f:
        f.write('// Auto-generated qrc_resources.cpp\n#include <vector>\n#include <string>\n')
        f.write('std::vector<std::string> demo_resources = {\n')
        for i,n in enumerate(names):
            comma=',' if i<len(names)-1 else ''
            f.write(f'  "{n}"{comma}\n')
        f.write('};\n')

if __name__=='__main__':
    if len(sys.argv)!=3:
        print('Usage: rcc.py <resources.qrc> <qrc_resources.cpp>')
        sys.exit(1)
    main(sys.argv[1],sys.argv[2])
