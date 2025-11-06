#include "service_17.h"

Service17::Service17() {}

void Service17::execute() {
    for (auto& cb : callbacks_) cb();
}

void Service17::registerCallback(std::function<void()> cb) {
    callbacks_.push_back(cb);
}
