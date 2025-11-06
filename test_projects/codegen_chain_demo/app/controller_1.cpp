#include "controller_1.h"
#include <iostream>

Controller1::Controller1() {
    service_ = std::make_unique<Service1>();
    model_ = std::make_shared<Model1>();
}

void Controller1::initialize() {
    service_->registerCallback([this]() {
        model_->process();
    });
}

void Controller1::run() {
    std::cout << "Controller1 running\n";
    service_->execute();
}
