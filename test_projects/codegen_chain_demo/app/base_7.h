#pragma once
#include <string>
#include <vector>
#include <memory>

class Base7 {
public:
    Base7();
    virtual ~Base7();
    virtual void process();
    virtual std::string getName() const;
protected:
    int id_7;
    std::string name_;
};
