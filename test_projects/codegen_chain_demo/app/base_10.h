#pragma once
#include <string>
#include <vector>
#include <memory>

class Base10 {
public:
    Base10();
    virtual ~Base10();
    virtual void process();
    virtual std::string getName() const;
protected:
    int id_10;
    std::string name_;
};
