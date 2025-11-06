#include "controller_20.h"
#include <iostream>

Controller20::Controller20() {
    service_ = std::make_unique<Service20>();
    model_ = std::make_shared<Model20>();
}

void Controller20::initialize() {
    service_->registerCallback([this]() {
        model_->process();
    });
}

void Controller20::run() {
    std::cout << "Controller20 running\n";
    service_->execute();
}
