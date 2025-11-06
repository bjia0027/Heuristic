#include "base_10.h"
#include <iostream>

Base10::Base10() : id_10(10), name_("Base10") {}

Base10::~Base10() {}

void Base10::process() {
    std::cout << "Base10::process() called\n";
}

std::string Base10::getName() const {
    return name_;
}
