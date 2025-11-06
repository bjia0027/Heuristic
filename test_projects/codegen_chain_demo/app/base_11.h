#pragma once
#include <string>
#include <vector>
#include <memory>

class Base11 {
public:
    Base11();
    virtual ~Base11();
    virtual void process();
    virtual std::string getName() const;
protected:
    int id_11;
    std::string name_;
};
