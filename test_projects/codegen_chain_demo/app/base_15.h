#pragma once
#include <string>
#include <vector>
#include <memory>

class Base15 {
public:
    Base15();
    virtual ~Base15();
    virtual void process();
    virtual std::string getName() const;
protected:
    int id_15;
    std::string name_;
};
