#include "controller_28.h"
#include <iostream>

Controller28::Controller28() {
    service_ = std::make_unique<Service28>();
    model_ = std::make_shared<Model28>();
}

void Controller28::initialize() {
    service_->registerCallback([this]() {
        model_->process();
    });
}

void Controller28::run() {
    std::cout << "Controller28 running\n";
    service_->execute();
}
