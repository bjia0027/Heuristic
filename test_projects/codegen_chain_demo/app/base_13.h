#pragma once
#include <string>
#include <vector>
#include <memory>

class Base13 {
public:
    Base13();
    virtual ~Base13();
    virtual void process();
    virtual std::string getName() const;
protected:
    int id_13;
    std::string name_;
};
