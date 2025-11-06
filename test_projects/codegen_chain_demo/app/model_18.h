#pragma once
#include "base_18.h"
#include <map>

class Model18 : public Base18 {
public:
    Model18();
    void process() override;
    void addData(int key, const std::string& value);
    std::map<int, std::string> getData() const;
private:
    std::map<int, std::string> data_;
};
