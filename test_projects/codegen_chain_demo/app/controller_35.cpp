#include "controller_35.h"
#include <iostream>

Controller35::Controller35() {
    service_ = std::make_unique<Service35>();
    model_ = std::make_shared<Model35>();
}

void Controller35::initialize() {
    service_->registerCallback([this]() {
        model_->process();
    });
}

void Controller35::run() {
    std::cout << "Controller35 running\n";
    service_->execute();
}
