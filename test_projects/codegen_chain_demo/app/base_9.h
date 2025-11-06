#pragma once
#include <string>
#include <vector>
#include <memory>

class Base9 {
public:
    Base9();
    virtual ~Base9();
    virtual void process();
    virtual std::string getName() const;
protected:
    int id_9;
    std::string name_;
};
