#include "controller_17.h"
#include <iostream>

Controller17::Controller17() {
    service_ = std::make_unique<Service17>();
    model_ = std::make_shared<Model17>();
}

void Controller17::initialize() {
    service_->registerCallback([this]() {
        model_->process();
    });
}

void Controller17::run() {
    std::cout << "Controller17 running\n";
    service_->execute();
}
