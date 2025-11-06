#include "service_16.h"

Service16::Service16() {}

void Service16::execute() {
    for (auto& cb : callbacks_) cb();
}

void Service16::registerCallback(std::function<void()> cb) {
    callbacks_.push_back(cb);
}
