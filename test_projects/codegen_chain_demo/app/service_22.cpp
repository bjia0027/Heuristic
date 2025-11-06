#include "service_22.h"

Service22::Service22() {}

void Service22::execute() {
    for (auto& cb : callbacks_) cb();
}

void Service22::registerCallback(std::function<void()> cb) {
    callbacks_.push_back(cb);
}
