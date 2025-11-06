#pragma once
#include <string>
#include <vector>
#include <memory>

class Base19 {
public:
    Base19();
    virtual ~Base19();
    virtual void process();
    virtual std::string getName() const;
protected:
    int id_19;
    std::string name_;
};
