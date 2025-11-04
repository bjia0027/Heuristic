#include "ops_gen.h"

int do_calc() {
  int v = 0;
  v += eval(OpKind::ADD, 3, 4);
  v += eval(OpKind::SUB, 10, 2);
  v += eval(OpKind::MUL, 2, 5);
  return v;
}
