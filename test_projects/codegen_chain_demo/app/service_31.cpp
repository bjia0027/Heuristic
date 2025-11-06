#include "service_31.h"

Service31::Service31() {}

void Service31::execute() {
    for (auto& cb : callbacks_) cb();
}

void Service31::registerCallback(std::function<void()> cb) {
    callbacks_.push_back(cb);
}
