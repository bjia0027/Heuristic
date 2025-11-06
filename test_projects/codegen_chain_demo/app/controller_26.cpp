#include "controller_26.h"
#include <iostream>

Controller26::Controller26() {
    service_ = std::make_unique<Service26>();
    model_ = std::make_shared<Model26>();
}

void Controller26::initialize() {
    service_->registerCallback([this]() {
        model_->process();
    });
}

void Controller26::run() {
    std::cout << "Controller26 running\n";
    service_->execute();
}
