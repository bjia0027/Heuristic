#pragma once
#include <string>
#include <vector>
#include <memory>

class Base4 {
public:
    Base4();
    virtual ~Base4();
    virtual void process();
    virtual std::string getName() const;
protected:
    int id_4;
    std::string name_;
};
