#include "controller_21.h"
#include <iostream>

Controller21::Controller21() {
    service_ = std::make_unique<Service21>();
    model_ = std::make_shared<Model21>();
}

void Controller21::initialize() {
    service_->registerCallback([this]() {
        model_->process();
    });
}

void Controller21::run() {
    std::cout << "Controller21 running\n";
    service_->execute();
}
