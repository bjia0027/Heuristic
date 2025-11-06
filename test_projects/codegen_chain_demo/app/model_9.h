#pragma once
#include "base_9.h"
#include <map>

class Model9 : public Base9 {
public:
    Model9();
    void process() override;
    void addData(int key, const std::string& value);
    std::map<int, std::string> getData() const;
private:
    std::map<int, std::string> data_;
};
