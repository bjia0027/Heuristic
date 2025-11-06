#include "controller_3.h"
#include <iostream>

Controller3::Controller3() {
    service_ = std::make_unique<Service3>();
    model_ = std::make_shared<Model3>();
}

void Controller3::initialize() {
    service_->registerCallback([this]() {
        model_->process();
    });
}

void Controller3::run() {
    std::cout << "Controller3 running\n";
    service_->execute();
}
