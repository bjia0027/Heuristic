#include "controller_4.h"
#include <iostream>

Controller4::Controller4() {
    service_ = std::make_unique<Service4>();
    model_ = std::make_shared<Model4>();
}

void Controller4::initialize() {
    service_->registerCallback([this]() {
        model_->process();
    });
}

void Controller4::run() {
    std::cout << "Controller4 running\n";
    service_->execute();
}
