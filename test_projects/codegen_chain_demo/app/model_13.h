#pragma once
#include "base_13.h"
#include <map>

class Model13 : public Base13 {
public:
    Model13();
    void process() override;
    void addData(int key, const std::string& value);
    std::map<int, std::string> getData() const;
private:
    std::map<int, std::string> data_;
};
