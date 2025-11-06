#pragma once
#include "base_4.h"
#include <map>

class Model24 : public Base4 {
public:
    Model24();
    void process() override;
    void addData(int key, const std::string& value);
    std::map<int, std::string> getData() const;
private:
    std::map<int, std::string> data_;
};
