#include "base_12.h"
#include <iostream>

Base12::Base12() : id_12(12), name_("Base12") {}

Base12::~Base12() {}

void Base12::process() {
    std::cout << "Base12::process() called\n";
}

std::string Base12::getName() const {
    return name_;
}
