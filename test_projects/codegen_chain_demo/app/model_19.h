#pragma once
#include "base_19.h"
#include <map>

class Model19 : public Base19 {
public:
    Model19();
    void process() override;
    void addData(int key, const std::string& value);
    std::map<int, std::string> getData() const;
private:
    std::map<int, std::string> data_;
};
