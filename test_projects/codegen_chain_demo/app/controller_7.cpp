#include "controller_7.h"
#include <iostream>

Controller7::Controller7() {
    service_ = std::make_unique<Service7>();
    model_ = std::make_shared<Model7>();
}

void Controller7::initialize() {
    service_->registerCallback([this]() {
        model_->process();
    });
}

void Controller7::run() {
    std::cout << "Controller7 running\n";
    service_->execute();
}
