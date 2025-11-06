#include "service_21.h"

Service21::Service21() {}

void Service21::execute() {
    for (auto& cb : callbacks_) cb();
}

void Service21::registerCallback(std::function<void()> cb) {
    callbacks_.push_back(cb);
}
