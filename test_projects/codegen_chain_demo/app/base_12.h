#pragma once
#include <string>
#include <vector>
#include <memory>

class Base12 {
public:
    Base12();
    virtual ~Base12();
    virtual void process();
    virtual std::string getName() const;
protected:
    int id_12;
    std::string name_;
};
