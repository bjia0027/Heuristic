#pragma once
#include <string>
#include <vector>
#include <memory>

class Base2 {
public:
    Base2();
    virtual ~Base2();
    virtual void process();
    virtual std::string getName() const;
protected:
    int id_2;
    std::string name_;
};
