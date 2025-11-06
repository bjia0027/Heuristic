#pragma once
#include "base_7.h"
#include <map>

class Model27 : public Base7 {
public:
    Model27();
    void process() override;
    void addData(int key, const std::string& value);
    std::map<int, std::string> getData() const;
private:
    std::map<int, std::string> data_;
};
