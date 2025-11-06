#include "base_14.h"
#include <iostream>

Base14::Base14() : id_14(14), name_("Base14") {}

Base14::~Base14() {}

void Base14::process() {
    std::cout << "Base14::process() called\n";
}

std::string Base14::getName() const {
    return name_;
}
