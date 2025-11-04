#include <string>
#include "messages.pb.h"

int ui_action() {
  Task t; t.id = 42; t.title = "Build";
  auto s = t.Serialize();
  return static_cast<int>(s.size());
}
