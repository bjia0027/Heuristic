#!/usr/bin/env python3
import sys
import re

"""
Minimal moc-like generator: scans a header for class with Q_OBJECT macro and emits
stub meta-object code that references a trivial method table.
"""

CLASS_RE=re.compile(r'class\s+(\w+)\s*[:{]')

def main(inp, outp):
    with open(inp,'r',encoding='utf-8') as f:
        content=f.read()
    m=CLASS_RE.search(content)
    cls=m.group(1) if m else 'Widget'
    with open(outp,'w',encoding='utf-8') as f:
        f.write('// Auto-generated moc file\n')
        f.write('#include <string>\n')
        f.write(f'static const char* qt_meta_stringdata_{cls}[] = {{"{cls}", "clicked()"}};\n')
        f.write(f'const char** metaInfo_{cls}() {{ return qt_meta_stringdata_{cls}; }}\n')

if __name__=='__main__':
    if len(sys.argv)!=3:
        print('Usage: moc.py <header.h> <moc_source.cpp>')
        sys.exit(1)
    main(sys.argv[1],sys.argv[2])
