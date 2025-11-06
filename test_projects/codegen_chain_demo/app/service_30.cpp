#include "service_30.h"

Service30::Service30() {}

void Service30::execute() {
    for (auto& cb : callbacks_) cb();
}

void Service30::registerCallback(std::function<void()> cb) {
    callbacks_.push_back(cb);
}
