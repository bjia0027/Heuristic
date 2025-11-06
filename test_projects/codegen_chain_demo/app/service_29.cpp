#include "service_29.h"

Service29::Service29() {}

void Service29::execute() {
    for (auto& cb : callbacks_) cb();
}

void Service29::registerCallback(std::function<void()> cb) {
    callbacks_.push_back(cb);
}
