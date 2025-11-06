#include "controller_2.h"
#include <iostream>

Controller2::Controller2() {
    service_ = std::make_unique<Service2>();
    model_ = std::make_shared<Model2>();
}

void Controller2::initialize() {
    service_->registerCallback([this]() {
        model_->process();
    });
}

void Controller2::run() {
    std::cout << "Controller2 running\n";
    service_->execute();
}
