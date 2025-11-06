#pragma once
#include <string>
#include <vector>
#include <memory>

class Base1 {
public:
    Base1();
    virtual ~Base1();
    virtual void process();
    virtual std::string getName() const;
protected:
    int id_1;
    std::string name_;
};
