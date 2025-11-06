#include "service_32.h"

Service32::Service32() {}

void Service32::execute() {
    for (auto& cb : callbacks_) cb();
}

void Service32::registerCallback(std::function<void()> cb) {
    callbacks_.push_back(cb);
}
