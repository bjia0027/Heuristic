#pragma once
#include <string>
#include <vector>
#include <memory>

class Base14 {
public:
    Base14();
    virtual ~Base14();
    virtual void process();
    virtual std::string getName() const;
protected:
    int id_14;
    std::string name_;
};
