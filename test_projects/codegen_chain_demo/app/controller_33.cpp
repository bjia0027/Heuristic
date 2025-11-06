#include "controller_33.h"
#include <iostream>

Controller33::Controller33() {
    service_ = std::make_unique<Service33>();
    model_ = std::make_shared<Model33>();
}

void Controller33::initialize() {
    service_->registerCallback([this]() {
        model_->process();
    });
}

void Controller33::run() {
    std::cout << "Controller33 running\n";
    service_->execute();
}
