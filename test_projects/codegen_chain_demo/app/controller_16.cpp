#include "controller_16.h"
#include <iostream>

Controller16::Controller16() {
    service_ = std::make_unique<Service16>();
    model_ = std::make_shared<Model16>();
}

void Controller16::initialize() {
    service_->registerCallback([this]() {
        model_->process();
    });
}

void Controller16::run() {
    std::cout << "Controller16 running\n";
    service_->execute();
}
