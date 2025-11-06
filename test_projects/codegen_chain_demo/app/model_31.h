#pragma once
#include "base_11.h"
#include <map>

class Model31 : public Base11 {
public:
    Model31();
    void process() override;
    void addData(int key, const std::string& value);
    std::map<int, std::string> getData() const;
private:
    std::map<int, std::string> data_;
};
