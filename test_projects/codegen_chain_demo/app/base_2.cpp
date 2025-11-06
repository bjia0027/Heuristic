#include "base_2.h"
#include <iostream>

Base2::Base2() : id_2(2), name_("Base2") {}

Base2::~Base2() {}

void Base2::process() {
    std::cout << "Base2::process() called\n";
}

std::string Base2::getName() const {
    return name_;
}
