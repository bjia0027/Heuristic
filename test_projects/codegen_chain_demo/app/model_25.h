#pragma once
#include "base_5.h"
#include <map>

class Model25 : public Base5 {
public:
    Model25();
    void process() override;
    void addData(int key, const std::string& value);
    std::map<int, std::string> getData() const;
private:
    std::map<int, std::string> data_;
};
