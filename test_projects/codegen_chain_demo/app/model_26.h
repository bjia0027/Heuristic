#pragma once
#include "base_6.h"
#include <map>

class Model26 : public Base6 {
public:
    Model26();
    void process() override;
    void addData(int key, const std::string& value);
    std::map<int, std::string> getData() const;
private:
    std::map<int, std::string> data_;
};
