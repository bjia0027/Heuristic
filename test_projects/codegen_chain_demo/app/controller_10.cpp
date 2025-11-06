#include "controller_10.h"
#include <iostream>

Controller10::Controller10() {
    service_ = std::make_unique<Service10>();
    model_ = std::make_shared<Model10>();
}

void Controller10::initialize() {
    service_->registerCallback([this]() {
        model_->process();
    });
}

void Controller10::run() {
    std::cout << "Controller10 running\n";
    service_->execute();
}
