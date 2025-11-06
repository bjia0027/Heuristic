#include "controller_36.h"
#include <iostream>

Controller36::Controller36() {
    service_ = std::make_unique<Service36>();
    model_ = std::make_shared<Model36>();
}

void Controller36::initialize() {
    service_->registerCallback([this]() {
        model_->process();
    });
}

void Controller36::run() {
    std::cout << "Controller36 running\n";
    service_->execute();
}
