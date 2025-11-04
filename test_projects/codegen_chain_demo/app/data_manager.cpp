#include "data_manager.h"
#include "messages.pb.h"
#include <iostream>

void DataManager::addData(int id, const std::string& value) {
  data_.push_back(value);
  Config cfg;
  cfg.version = id;
  cfg.name = value;
  std::cout << "Config: " << cfg.Serialize() << "\n";
}

std::vector<std::string> DataManager::getData() const {
  return data_;
}
