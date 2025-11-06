#include "controller_8.h"
#include <iostream>

Controller8::Controller8() {
    service_ = std::make_unique<Service8>();
    model_ = std::make_shared<Model8>();
}

void Controller8::initialize() {
    service_->registerCallback([this]() {
        model_->process();
    });
}

void Controller8::run() {
    std::cout << "Controller8 running\n";
    service_->execute();
}
