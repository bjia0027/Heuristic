#pragma once
#include "base_10.h"
#include <map>

class Model10 : public Base10 {
public:
    Model10();
    void process() override;
    void addData(int key, const std::string& value);
    std::map<int, std::string> getData() const;
private:
    std::map<int, std::string> data_;
};
