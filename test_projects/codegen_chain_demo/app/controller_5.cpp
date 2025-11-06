#include "controller_5.h"
#include <iostream>

Controller5::Controller5() {
    service_ = std::make_unique<Service5>();
    model_ = std::make_shared<Model5>();
}

void Controller5::initialize() {
    service_->registerCallback([this]() {
        model_->process();
    });
}

void Controller5::run() {
    std::cout << "Controller5 running\n";
    service_->execute();
}
