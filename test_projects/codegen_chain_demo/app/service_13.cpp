#include "service_13.h"

Service13::Service13() {}

void Service13::execute() {
    for (auto& cb : callbacks_) cb();
}

void Service13::registerCallback(std::function<void()> cb) {
    callbacks_.push_back(cb);
}
