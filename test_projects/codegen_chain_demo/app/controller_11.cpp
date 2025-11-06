#include "controller_11.h"
#include <iostream>

Controller11::Controller11() {
    service_ = std::make_unique<Service11>();
    model_ = std::make_shared<Model11>();
}

void Controller11::initialize() {
    service_->registerCallback([this]() {
        model_->process();
    });
}

void Controller11::run() {
    std::cout << "Controller11 running\n";
    service_->execute();
}
