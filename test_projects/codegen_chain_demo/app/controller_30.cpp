#include "controller_30.h"
#include <iostream>

Controller30::Controller30() {
    service_ = std::make_unique<Service30>();
    model_ = std::make_shared<Model30>();
}

void Controller30::initialize() {
    service_->registerCallback([this]() {
        model_->process();
    });
}

void Controller30::run() {
    std::cout << "Controller30 running\n";
    service_->execute();
}
