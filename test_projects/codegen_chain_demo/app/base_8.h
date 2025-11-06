#pragma once
#include <string>
#include <vector>
#include <memory>

class Base8 {
public:
    Base8();
    virtual ~Base8();
    virtual void process();
    virtual std::string getName() const;
protected:
    int id_8;
    std::string name_;
};
