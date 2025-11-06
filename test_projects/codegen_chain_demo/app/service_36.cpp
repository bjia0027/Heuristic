#include "service_36.h"

Service36::Service36() {}

void Service36::execute() {
    for (auto& cb : callbacks_) cb();
}

void Service36::registerCallback(std::function<void()> cb) {
    callbacks_.push_back(cb);
}
