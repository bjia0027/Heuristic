#include "data_manager.h"
#include "ops_gen.h"
#include <iostream>

int analyze_data() {
  DataManager dm;
  dm.addData(1, "sample");
  dm.addData(2, "test");
  
  int x = eval(OpKind::NOT, 0, 0);
  std::cout << "Analyze result: " << x << "\n";
  return x;
}
