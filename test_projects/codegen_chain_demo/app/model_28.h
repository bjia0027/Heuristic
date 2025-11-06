#pragma once
#include "base_8.h"
#include <map>

class Model28 : public Base8 {
public:
    Model28();
    void process() override;
    void addData(int key, const std::string& value);
    std::map<int, std::string> getData() const;
private:
    std::map<int, std::string> data_;
};
