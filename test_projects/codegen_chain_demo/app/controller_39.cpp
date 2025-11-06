#include "controller_39.h"
#include <iostream>

Controller39::Controller39() {
    service_ = std::make_unique<Service39>();
    model_ = std::make_shared<Model39>();
}

void Controller39::initialize() {
    service_->registerCallback([this]() {
        model_->process();
    });
}

void Controller39::run() {
    std::cout << "Controller39 running\n";
    service_->execute();
}
