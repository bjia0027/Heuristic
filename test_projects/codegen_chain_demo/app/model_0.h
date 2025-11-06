#pragma once
#include "base_0.h"
#include <map>

class Model0 : public Base0 {
public:
    Model0();
    void process() override;
    void addData(int key, const std::string& value);
    std::map<int, std::string> getData() const;
private:
    std::map<int, std::string> data_;
};
