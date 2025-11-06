#include "base_3.h"
#include <iostream>

Base3::Base3() : id_3(3), name_("Base3") {}

Base3::~Base3() {}

void Base3::process() {
    std::cout << "Base3::process() called\n";
}

std::string Base3::getName() const {
    return name_;
}
