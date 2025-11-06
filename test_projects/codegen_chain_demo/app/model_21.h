#pragma once
#include "base_1.h"
#include <map>

class Model21 : public Base1 {
public:
    Model21();
    void process() override;
    void addData(int key, const std::string& value);
    std::map<int, std::string> getData() const;
private:
    std::map<int, std::string> data_;
};
