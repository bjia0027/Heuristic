#pragma once
#include <string>
#include <vector>
#include <memory>

class Base5 {
public:
    Base5();
    virtual ~Base5();
    virtual void process();
    virtual std::string getName() const;
protected:
    int id_5;
    std::string name_;
};
