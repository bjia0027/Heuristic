#pragma once
#include "base_12.h"
#include <map>

class Model32 : public Base12 {
public:
    Model32();
    void process() override;
    void addData(int key, const std::string& value);
    std::map<int, std::string> getData() const;
private:
    std::map<int, std::string> data_;
};
