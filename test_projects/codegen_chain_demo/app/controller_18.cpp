#include "controller_18.h"
#include <iostream>

Controller18::Controller18() {
    service_ = std::make_unique<Service18>();
    model_ = std::make_shared<Model18>();
}

void Controller18::initialize() {
    service_->registerCallback([this]() {
        model_->process();
    });
}

void Controller18::run() {
    std::cout << "Controller18 running\n";
    service_->execute();
}
