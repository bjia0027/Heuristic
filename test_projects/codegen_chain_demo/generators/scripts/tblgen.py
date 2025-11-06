#!/usr/bin/env python3
import sys

"""
Very small TableGen-like generator.
Input format (ops.td):
  op ADD
  op SUB
  op MUL
Generates ops_gen.h/.cpp with an enum and a simple eval function.
"""

def parse_ops(path):
    ops = []
    with open(path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            parts = line.split()
            if len(parts) == 2 and parts[0].lower() == 'op':
                ops.append(parts[1])
    return ops

def gen_header(ops, out_h):
    with open(out_h, 'w', encoding='utf-8') as f:
        # Extract base name from output path for header guard
        import os
        base_name = os.path.basename(out_h).replace('.', '_').upper()
        f.write(f'// Auto-generated {os.path.basename(out_h)}\n#pragma once\n\n')
        f.write('enum class OpKind {\n')
        for i, op in enumerate(ops):
            comma = ',' if i < len(ops)-1 else ''
            f.write(f'  {op}{comma}\n')
        f.write('};\n\n')
        f.write('int eval(OpKind op, int a, int b);\n')

def gen_source(ops, out_cpp, header_name):
    with open(out_cpp, 'w', encoding='utf-8') as f:
        import os
        f.write(f'// Auto-generated {os.path.basename(out_cpp)}\n')
        f.write(f'#include "{header_name}"\n')
        f.write('int eval(OpKind op, int a, int b) {\n')
        f.write('  switch(op){\n')
        for op in ops:
            if op == 'ADD':
                f.write('    case OpKind::ADD: return a + b;\n')
            elif op == 'SUB':
                f.write('    case OpKind::SUB: return a - b;\n')
            elif op == 'MUL':
                f.write('    case OpKind::MUL: return a * b;\n')
            elif op == 'DIV':
                f.write('    case OpKind::DIV: return b ? a / b : 0;\n')
            elif op == 'AND':
                f.write('    case OpKind::AND: return a & b;\n')
            elif op == 'OR':
                f.write('    case OpKind::OR: return a | b;\n')
            elif op == 'NOT':
                f.write('    case OpKind::NOT: return ~a;\n')
            elif op == 'SHL':
                f.write('    case OpKind::SHL: return a << b;\n')
            elif op == 'SHR':
                f.write('    case OpKind::SHR: return a >> b;\n')
            else:
                f.write(f'    case OpKind::{op}: return a ^ b;\n')
        f.write('  }\n  return 0;\n}\n')

def main(inp, out_h, out_cpp):
    import os
    ops = parse_ops(inp)
    if not ops:
        ops = ['ADD','SUB','MUL','DIV']
    gen_header(ops, out_h)
    # Pass just the basename of the header file
    gen_source(ops, out_cpp, os.path.basename(out_h))

if __name__ == '__main__':
    if len(sys.argv) != 4:
        print('Usage: tblgen.py <ops.td> <ops_gen.h> <ops_gen.cpp>')
        sys.exit(1)
    main(sys.argv[1], sys.argv[2], sys.argv[3])
