#pragma once
#include "base_1.h"
#include <map>

class Model1 : public Base1 {
public:
    Model1();
    void process() override;
    void addData(int key, const std::string& value);
    std::map<int, std::string> getData() const;
private:
    std::map<int, std::string> data_;
};
