#include "controller_15.h"
#include <iostream>

Controller15::Controller15() {
    service_ = std::make_unique<Service15>();
    model_ = std::make_shared<Model15>();
}

void Controller15::initialize() {
    service_->registerCallback([this]() {
        model_->process();
    });
}

void Controller15::run() {
    std::cout << "Controller15 running\n";
    service_->execute();
}
