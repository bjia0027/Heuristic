#include "controller_25.h"
#include <iostream>

Controller25::Controller25() {
    service_ = std::make_unique<Service25>();
    model_ = std::make_shared<Model25>();
}

void Controller25::initialize() {
    service_->registerCallback([this]() {
        model_->process();
    });
}

void Controller25::run() {
    std::cout << "Controller25 running\n";
    service_->execute();
}
