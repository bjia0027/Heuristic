#pragma once
#include <vector>
#include <string>

class DataManager {
public:
  void addData(int id, const std::string& value);
  std::vector<std::string> getData() const;
private:
  std::vector<std::string> data_;
};
