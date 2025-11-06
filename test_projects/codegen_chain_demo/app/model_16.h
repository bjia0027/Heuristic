#pragma once
#include "base_16.h"
#include <map>

class Model16 : public Base16 {
public:
    Model16();
    void process() override;
    void addData(int key, const std::string& value);
    std::map<int, std::string> getData() const;
private:
    std::map<int, std::string> data_;
};
