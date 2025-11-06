#include "controller_9.h"
#include <iostream>

Controller9::Controller9() {
    service_ = std::make_unique<Service9>();
    model_ = std::make_shared<Model9>();
}

void Controller9::initialize() {
    service_->registerCallback([this]() {
        model_->process();
    });
}

void Controller9::run() {
    std::cout << "Controller9 running\n";
    service_->execute();
}
