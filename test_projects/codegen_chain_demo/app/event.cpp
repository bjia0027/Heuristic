#include "messages.pb.h"
#include <iostream>

void send_event(int ts, const std::string& type) {
  Event e;
  e.timestamp = ts;
  e.type = type;
  std::cout << "Event: " << e.Serialize() << "\n";
}
