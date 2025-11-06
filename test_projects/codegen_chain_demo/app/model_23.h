#pragma once
#include "base_3.h"
#include <map>

class Model23 : public Base3 {
public:
    Model23();
    void process() override;
    void addData(int key, const std::string& value);
    std::map<int, std::string> getData() const;
private:
    std::map<int, std::string> data_;
};
