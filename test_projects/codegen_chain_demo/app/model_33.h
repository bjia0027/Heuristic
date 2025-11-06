#pragma once
#include "base_13.h"
#include <map>

class Model33 : public Base13 {
public:
    Model33();
    void process() override;
    void addData(int key, const std::string& value);
    std::map<int, std::string> getData() const;
private:
    std::map<int, std::string> data_;
};
