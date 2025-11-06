#include "controller_12.h"
#include <iostream>

Controller12::Controller12() {
    service_ = std::make_unique<Service12>();
    model_ = std::make_shared<Model12>();
}

void Controller12::initialize() {
    service_->registerCallback([this]() {
        model_->process();
    });
}

void Controller12::run() {
    std::cout << "Controller12 running\n";
    service_->execute();
}
