#pragma once
#include "base_11.h"
#include <map>

class Model11 : public Base11 {
public:
    Model11();
    void process() override;
    void addData(int key, const std::string& value);
    std::map<int, std::string> getData() const;
private:
    std::map<int, std::string> data_;
};
