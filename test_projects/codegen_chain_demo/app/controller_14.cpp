#include "controller_14.h"
#include <iostream>

Controller14::Controller14() {
    service_ = std::make_unique<Service14>();
    model_ = std::make_shared<Model14>();
}

void Controller14::initialize() {
    service_->registerCallback([this]() {
        model_->process();
    });
}

void Controller14::run() {
    std::cout << "Controller14 running\n";
    service_->execute();
}
