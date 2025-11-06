#include "service_19.h"

Service19::Service19() {}

void Service19::execute() {
    for (auto& cb : callbacks_) cb();
}

void Service19::registerCallback(std::function<void()> cb) {
    callbacks_.push_back(cb);
}
