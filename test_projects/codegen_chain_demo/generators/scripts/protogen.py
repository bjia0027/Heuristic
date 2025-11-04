#!/usr/bin/env python3
import sys

"""
Tiny proto-like generator:
Input example:
  message Person { int id; string name; }
Generates messages.pb.h/.cc with a struct and trivial serialize stubs.
"""

def parse_messages(path):
    messages = []
    with open(path, 'r', encoding='utf-8') as f:
        content = f.read()
    # Extremely naive parser
    for block in content.split('message '):
        block = block.strip()
        if not block:
            continue
        name, rest = block.split('{', 1)
        name = name.strip().split()[0]
        fields_part = rest.split('}',1)[0]
        fields = []
        for line in fields_part.split(';'):
            line=line.strip()
            if not line:
                continue
            parts=line.split()
            if len(parts)>=2:
                ftype=parts[0]
                fname=parts[1].strip(';')
                fields.append((ftype,fname))
        messages.append((name,fields))
    return messages

def gen_h(messages, out_h):
    with open(out_h,'w',encoding='utf-8') as f:
        f.write('// Auto-generated messages.pb.h\n#pragma once\n#include <string>\n\n')
        for name, fields in messages:
            f.write(f'struct {name} {{\n')
            for t,n in fields:
                cpp_t = 'int' if t=='int' else 'std::string'
                f.write(f'  {cpp_t} {n};\n')
            f.write('  std::string Serialize() const;\n')
            f.write('  void Parse(const std::string&);\n')
            f.write('};\n\n')

def gen_cc(messages, out_cc):
    with open(out_cc,'w',encoding='utf-8') as f:
        f.write('// Auto-generated messages.pb.cc\n#include "messages.pb.h"\n\n')
        for name, fields in messages:
            f.write(f'std::string {name}::Serialize() const {{ return "{name}"; }}\n')
            f.write(f'void {name}::Parse(const std::string&) {{ /*noop*/ }}\n\n')

def main(inp, out_h, out_cc):
    messages = parse_messages(inp)
    if not messages:
        messages=[('Person',[('int','id'),('string','name')])]
    gen_h(messages,out_h)
    gen_cc(messages,out_cc)

if __name__=='__main__':
    if len(sys.argv)!=4:
        print('Usage: protogen.py <.proto> <pb.h> <pb.cc>')
        sys.exit(1)
    main(sys.argv[1],sys.argv[2],sys.argv[3])
