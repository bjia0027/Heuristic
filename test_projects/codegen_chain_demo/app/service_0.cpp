#include "service_0.h"

Service0::Service0() {}

void Service0::execute() {
    for (auto& cb : callbacks_) cb();
}

void Service0::registerCallback(std::function<void()> cb) {
    callbacks_.push_back(cb);
}
