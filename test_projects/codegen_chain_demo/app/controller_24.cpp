#include "controller_24.h"
#include <iostream>

Controller24::Controller24() {
    service_ = std::make_unique<Service24>();
    model_ = std::make_shared<Model24>();
}

void Controller24::initialize() {
    service_->registerCallback([this]() {
        model_->process();
    });
}

void Controller24::run() {
    std::cout << "Controller24 running\n";
    service_->execute();
}
