#include "controller_34.h"
#include <iostream>

Controller34::Controller34() {
    service_ = std::make_unique<Service34>();
    model_ = std::make_shared<Model34>();
}

void Controller34::initialize() {
    service_->registerCallback([this]() {
        model_->process();
    });
}

void Controller34::run() {
    std::cout << "Controller34 running\n";
    service_->execute();
}
