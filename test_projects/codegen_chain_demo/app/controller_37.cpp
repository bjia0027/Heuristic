#include "controller_37.h"
#include <iostream>

Controller37::Controller37() {
    service_ = std::make_unique<Service37>();
    model_ = std::make_shared<Model37>();
}

void Controller37::initialize() {
    service_->registerCallback([this]() {
        model_->process();
    });
}

void Controller37::run() {
    std::cout << "Controller37 running\n";
    service_->execute();
}
