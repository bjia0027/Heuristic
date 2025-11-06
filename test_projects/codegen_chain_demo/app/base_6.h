#pragma once
#include <string>
#include <vector>
#include <memory>

class Base6 {
public:
    Base6();
    virtual ~Base6();
    virtual void process();
    virtual std::string getName() const;
protected:
    int id_6;
    std::string name_;
};
