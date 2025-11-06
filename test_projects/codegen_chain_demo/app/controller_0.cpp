#include "controller_0.h"
#include <iostream>

Controller0::Controller0() {
    service_ = std::make_unique<Service0>();
    model_ = std::make_shared<Model0>();
}

void Controller0::initialize() {
    service_->registerCallback([this]() {
        model_->process();
    });
}

void Controller0::run() {
    std::cout << "Controller0 running\n";
    service_->execute();
}
