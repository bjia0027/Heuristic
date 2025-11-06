#include "controller_13.h"
#include <iostream>

Controller13::Controller13() {
    service_ = std::make_unique<Service13>();
    model_ = std::make_shared<Model13>();
}

void Controller13::initialize() {
    service_->registerCallback([this]() {
        model_->process();
    });
}

void Controller13::run() {
    std::cout << "Controller13 running\n";
    service_->execute();
}
