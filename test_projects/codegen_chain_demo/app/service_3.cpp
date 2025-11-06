#include "service_3.h"

Service3::Service3() {}

void Service3::execute() {
    for (auto& cb : callbacks_) cb();
}

void Service3::registerCallback(std::function<void()> cb) {
    callbacks_.push_back(cb);
}
