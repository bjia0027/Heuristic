#include "controller_6.h"
#include <iostream>

Controller6::Controller6() {
    service_ = std::make_unique<Service6>();
    model_ = std::make_shared<Model6>();
}

void Controller6::initialize() {
    service_->registerCallback([this]() {
        model_->process();
    });
}

void Controller6::run() {
    std::cout << "Controller6 running\n";
    service_->execute();
}
