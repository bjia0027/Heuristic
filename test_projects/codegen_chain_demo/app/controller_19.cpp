#include "controller_19.h"
#include <iostream>

Controller19::Controller19() {
    service_ = std::make_unique<Service19>();
    model_ = std::make_shared<Model19>();
}

void Controller19::initialize() {
    service_->registerCallback([this]() {
        model_->process();
    });
}

void Controller19::run() {
    std::cout << "Controller19 running\n";
    service_->execute();
}
