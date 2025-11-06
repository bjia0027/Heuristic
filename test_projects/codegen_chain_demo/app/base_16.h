#pragma once
#include <string>
#include <vector>
#include <memory>

class Base16 {
public:
    Base16();
    virtual ~Base16();
    virtual void process();
    virtual std::string getName() const;
protected:
    int id_16;
    std::string name_;
};
