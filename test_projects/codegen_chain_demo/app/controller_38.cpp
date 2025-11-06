#include "controller_38.h"
#include <iostream>

Controller38::Controller38() {
    service_ = std::make_unique<Service38>();
    model_ = std::make_shared<Model38>();
}

void Controller38::initialize() {
    service_->registerCallback([this]() {
        model_->process();
    });
}

void Controller38::run() {
    std::cout << "Controller38 running\n";
    service_->execute();
}
