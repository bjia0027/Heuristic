#pragma once
#include <string>
#include <vector>
#include <memory>

class Base17 {
public:
    Base17();
    virtual ~Base17();
    virtual void process();
    virtual std::string getName() const;
protected:
    int id_17;
    std::string name_;
};
