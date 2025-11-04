#include "ops_gen.h"
#include <iostream>

int process_operations() {
  int result = 0;
  result += eval(OpKind::AND, 15, 7);
  result += eval(OpKind::OR, 8, 4);
  result += eval(OpKind::SHL, 2, 3);
  result += eval(OpKind::SHR, 64, 2);
  std::cout << "Process operations result: " << result << "\n";
  return result;
}
