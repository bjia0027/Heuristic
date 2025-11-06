#include "controller_31.h"
#include <iostream>

Controller31::Controller31() {
    service_ = std::make_unique<Service31>();
    model_ = std::make_shared<Model31>();
}

void Controller31::initialize() {
    service_->registerCallback([this]() {
        model_->process();
    });
}

void Controller31::run() {
    std::cout << "Controller31 running\n";
    service_->execute();
}
