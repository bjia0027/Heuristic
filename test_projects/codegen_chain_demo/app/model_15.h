#pragma once
#include "base_15.h"
#include <map>

class Model15 : public Base15 {
public:
    Model15();
    void process() override;
    void addData(int key, const std::string& value);
    std::map<int, std::string> getData() const;
private:
    std::map<int, std::string> data_;
};
