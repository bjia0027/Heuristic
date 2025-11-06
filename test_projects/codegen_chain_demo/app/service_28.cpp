#include "service_28.h"

Service28::Service28() {}

void Service28::execute() {
    for (auto& cb : callbacks_) cb();
}

void Service28::registerCallback(std::function<void()> cb) {
    callbacks_.push_back(cb);
}
