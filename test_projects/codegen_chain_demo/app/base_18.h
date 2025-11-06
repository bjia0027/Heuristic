#pragma once
#include <string>
#include <vector>
#include <memory>

class Base18 {
public:
    Base18();
    virtual ~Base18();
    virtual void process();
    virtual std::string getName() const;
protected:
    int id_18;
    std::string name_;
};
