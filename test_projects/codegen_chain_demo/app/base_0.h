#pragma once
#include <string>
#include <vector>
#include <memory>

class Base0 {
public:
    Base0();
    virtual ~Base0();
    virtual void process();
    virtual std::string getName() const;
protected:
    int id_0;
    std::string name_;
};
