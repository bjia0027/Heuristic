#pragma once
#include "base_14.h"
#include <map>

class Model14 : public Base14 {
public:
    Model14();
    void process() override;
    void addData(int key, const std::string& value);
    std::map<int, std::string> getData() const;
private:
    std::map<int, std::string> data_;
};
