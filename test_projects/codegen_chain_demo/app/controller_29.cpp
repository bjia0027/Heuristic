#include "controller_29.h"
#include <iostream>

Controller29::Controller29() {
    service_ = std::make_unique<Service29>();
    model_ = std::make_shared<Model29>();
}

void Controller29::initialize() {
    service_->registerCallback([this]() {
        model_->process();
    });
}

void Controller29::run() {
    std::cout << "Controller29 running\n";
    service_->execute();
}
