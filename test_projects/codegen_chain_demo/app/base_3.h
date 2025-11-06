#pragma once
#include <string>
#include <vector>
#include <memory>

class Base3 {
public:
    Base3();
    virtual ~Base3();
    virtual void process();
    virtual std::string getName() const;
protected:
    int id_3;
    std::string name_;
};
