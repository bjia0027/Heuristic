#include "base_13.h"
#include <iostream>

Base13::Base13() : id_13(13), name_("Base13") {}

Base13::~Base13() {}

void Base13::process() {
    std::cout << "Base13::process() called\n";
}

std::string Base13::getName() const {
    return name_;
}
