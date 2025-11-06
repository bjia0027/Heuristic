#include "controller_27.h"
#include <iostream>

Controller27::Controller27() {
    service_ = std::make_unique<Service27>();
    model_ = std::make_shared<Model27>();
}

void Controller27::initialize() {
    service_->registerCallback([this]() {
        model_->process();
    });
}

void Controller27::run() {
    std::cout << "Controller27 running\n";
    service_->execute();
}
