#include "controller_23.h"
#include <iostream>

Controller23::Controller23() {
    service_ = std::make_unique<Service23>();
    model_ = std::make_shared<Model23>();
}

void Controller23::initialize() {
    service_->registerCallback([this]() {
        model_->process();
    });
}

void Controller23::run() {
    std::cout << "Controller23 running\n";
    service_->execute();
}
