#include "controller_32.h"
#include <iostream>

Controller32::Controller32() {
    service_ = std::make_unique<Service32>();
    model_ = std::make_shared<Model32>();
}

void Controller32::initialize() {
    service_->registerCallback([this]() {
        model_->process();
    });
}

void Controller32::run() {
    std::cout << "Controller32 running\n";
    service_->execute();
}
