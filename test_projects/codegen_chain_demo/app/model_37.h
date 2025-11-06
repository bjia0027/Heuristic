#pragma once
#include "base_17.h"
#include <map>

class Model37 : public Base17 {
public:
    Model37();
    void process() override;
    void addData(int key, const std::string& value);
    std::map<int, std::string> getData() const;
private:
    std::map<int, std::string> data_;
};
