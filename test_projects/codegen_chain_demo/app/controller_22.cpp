#include "controller_22.h"
#include <iostream>

Controller22::Controller22() {
    service_ = std::make_unique<Service22>();
    model_ = std::make_shared<Model22>();
}

void Controller22::initialize() {
    service_->registerCallback([this]() {
        model_->process();
    });
}

void Controller22::run() {
    std::cout << "Controller22 running\n";
    service_->execute();
}
