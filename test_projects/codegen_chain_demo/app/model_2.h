#pragma once
#include "base_2.h"
#include <map>

class Model2 : public Base2 {
public:
    Model2();
    void process() override;
    void addData(int key, const std::string& value);
    std::map<int, std::string> getData() const;
private:
    std::map<int, std::string> data_;
};
